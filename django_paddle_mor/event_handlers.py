from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import WebhookEndpoint, WebhookEvent
from .sanitization import redact_sensitive_fields
from .signals import webhook_post_process, webhook_pre_process, webhook_processing_error
from .sync import resource_name_for_event_type, sync_payload

RESOURCE_ORDERING_KEYS = ("updated_at", "effective_at", "occurred_at")
PERSISTED_WEBHOOK_HEADER_NAMES = frozenset(
    {
        "content-type",
        "paddle-signature",
        "user-agent",
    }
)
PENDING_WEBHOOK_LEASE = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class WebhookIngestionResult:
    webhook_event: WebhookEvent
    synced_resource: object | None
    created: bool
    sync_error: str = ""


def _raise_first_signal_error(signal_responses) -> None:
    for _receiver, response in signal_responses:
        if isinstance(response, Exception):
            raise response


def build_webhook_dedupe_key(
    payload: dict[str, Any],
    *,
    endpoint: WebhookEndpoint | None = None,
    dedupe_scope: str | None = None,
) -> str:
    endpoint_scope = dedupe_scope or (str(endpoint.uuid) if endpoint else "global")
    event_id = payload.get("event_id") or payload.get("id") or payload.get("notification_id")
    if event_id:
        return f"event:{endpoint_scope}:{event_id}"

    payload_hash = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"payload:{endpoint_scope}:{payload_hash}"


def build_legacy_webhook_dedupe_key(payload: dict[str, Any]) -> str:
    event_id = payload.get("event_id") or payload.get("id") or payload.get("notification_id")
    if event_id:
        return f"event:{event_id}"

    payload_hash = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"payload:{payload_hash}"


def filter_persisted_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}

    return {
        key: value
        for key, value in headers.items()
        if key.lower() in PERSISTED_WEBHOOK_HEADER_NAMES
    }


def ingest_webhook_payload(
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    signature_verified: bool = True,
    endpoint: WebhookEndpoint | None = None,
    dedupe_scope: str | None = None,
    force_process: bool = False,
) -> WebhookIngestionResult:
    event_type = str(payload.get("event_type") or payload.get("type") or "")
    resource_name = resource_name_for_event_type(event_type) or ""
    sanitized_payload = redact_sensitive_fields(payload)
    raw_occurred_at = payload.get("occurred_at")
    if raw_occurred_at is not None and not isinstance(raw_occurred_at, str):
        raise ValueError("Webhook 'occurred_at' must be a string when provided.")
    occurred_at = parse_datetime(raw_occurred_at) if raw_occurred_at else None
    dedupe_scope = dedupe_scope or (str(endpoint.uuid) if endpoint else "global")
    dedupe_key = build_webhook_dedupe_key(payload, endpoint=endpoint, dedupe_scope=dedupe_scope)
    event_id = str(
        payload.get("event_id") or payload.get("id") or payload.get("notification_id") or ""
    )

    if resource_name and not isinstance(payload.get("data"), dict):
        raise ValueError("Webhook resource payloads must include a JSON object in 'data'.")

    with transaction.atomic():
        created = False
        try:
            webhook_event = WebhookEvent.objects.select_for_update().get(dedupe_key=dedupe_key)
        except WebhookEvent.DoesNotExist:
            legacy_dedupe_key = (
                build_legacy_webhook_dedupe_key(payload) if dedupe_scope == "global" else None
            )
            try:
                webhook_event = WebhookEvent.objects.select_for_update().get(
                    dedupe_key=legacy_dedupe_key
                )
                webhook_event.dedupe_key = dedupe_key
            except WebhookEvent.DoesNotExist:
                try:
                    with transaction.atomic():
                        webhook_event = WebhookEvent.objects.create(dedupe_key=dedupe_key)
                    created = True
                except IntegrityError:
                    webhook_event = WebhookEvent.objects.select_for_update().get(
                        dedupe_key=dedupe_key
                    )
        if not created and not force_process:
            if webhook_event.dedupe_key != dedupe_key or webhook_event.dedupe_scope != dedupe_scope:
                webhook_event.dedupe_key = dedupe_key
                webhook_event.dedupe_scope = dedupe_scope
                webhook_event.save(update_fields=["dedupe_key", "dedupe_scope", "updated_at"])
            if webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED:
                return WebhookIngestionResult(
                    webhook_event=webhook_event,
                    synced_resource=None,
                    created=False,
                    sync_error="",
                )
            if webhook_event.processing_state == WebhookEvent.ProcessingState.PENDING:
                lease_cutoff = timezone.now() - PENDING_WEBHOOK_LEASE
                if webhook_event.processed_at and webhook_event.processed_at >= lease_cutoff:
                    return WebhookIngestionResult(
                        webhook_event=webhook_event,
                        synced_resource=None,
                        created=False,
                        sync_error="",
                    )

        webhook_event.endpoint = endpoint
        webhook_event.dedupe_scope = dedupe_scope
        webhook_event.event_id = event_id
        webhook_event.event_type = event_type
        webhook_event.resource_name = resource_name
        webhook_event.signature_verified = signature_verified
        webhook_event.processing_state = WebhookEvent.ProcessingState.PENDING
        webhook_event.processing_attempts += 1
        webhook_event.payload = sanitized_payload
        webhook_event.headers = filter_persisted_headers(headers)
        webhook_event.sync_error = ""
        webhook_event.occurred_at = occurred_at
        webhook_event.last_error_at = None
        webhook_event.processed_at = timezone.now()
        webhook_event.save()

    synced_resource = None
    sync_error = ""
    try:
        _raise_first_signal_error(
            webhook_pre_process.send_robust(
                sender=WebhookEvent,
                webhook_event=webhook_event,
                endpoint=endpoint,
                created=created,
            )
        )

        if resource_name:
            resource_payload = dict(payload["data"])
            if not any(resource_payload.get(key) for key in RESOURCE_ORDERING_KEYS) and payload.get(
                "occurred_at"
            ):
                resource_payload["occurred_at"] = payload["occurred_at"]

            synced_resource = sync_payload(resource_name, resource_payload, source="webhook")

        webhook_event.processing_state = WebhookEvent.ProcessingState.PROCESSED
        webhook_event.sync_error = ""
        webhook_event.last_error_at = None
        webhook_event.processed_at = timezone.now()
        webhook_event.save(
            update_fields=[
                "processing_state",
                "sync_error",
                "last_error_at",
                "processed_at",
                "updated_at",
            ]
        )
    except Exception as exc:
        sync_error = str(exc)
        webhook_event.processing_state = WebhookEvent.ProcessingState.FAILED
        webhook_event.sync_error = sync_error
        webhook_event.last_error_at = timezone.now()
        webhook_event.processed_at = timezone.now()
        webhook_event.save(
            update_fields=[
                "processing_state",
                "sync_error",
                "last_error_at",
                "processed_at",
                "updated_at",
            ]
        )
        webhook_processing_error.send_robust(
            sender=WebhookEvent,
            webhook_event=webhook_event,
            endpoint=endpoint,
            exception=exc,
        )
    webhook_post_process.send_robust(
        sender=WebhookEvent,
        webhook_event=webhook_event,
        endpoint=endpoint,
        created=created,
        success=not bool(sync_error),
        synced_resource=synced_resource,
        sync_error=sync_error,
    )

    return WebhookIngestionResult(
        webhook_event=webhook_event,
        synced_resource=synced_resource,
        created=created,
        sync_error=sync_error,
    )


def reprocess_webhook_event(webhook_event: WebhookEvent) -> WebhookIngestionResult:
    if not isinstance(webhook_event.payload, dict):
        raise ValueError("Webhook events can only be reprocessed when payload is a JSON object.")

    return ingest_webhook_payload(
        webhook_event.payload,
        headers=webhook_event.headers,
        signature_verified=webhook_event.signature_verified,
        endpoint=webhook_event.endpoint,
        dedupe_scope=webhook_event.dedupe_scope,
        force_process=True,
    )
