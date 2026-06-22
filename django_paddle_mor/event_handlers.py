from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import WebhookEvent
from .sanitization import redact_sensitive_fields
from .sync import resource_name_for_event_type, sync_payload

RESOURCE_ORDERING_KEYS = ("updated_at", "effective_at", "occurred_at")
PERSISTED_WEBHOOK_HEADER_NAMES = frozenset(
    {
        "content-type",
        "paddle-signature",
        "user-agent",
    }
)


@dataclass(frozen=True, slots=True)
class WebhookIngestionResult:
    webhook_event: WebhookEvent
    synced_resource: object | None
    created: bool
    sync_error: str = ""


def build_webhook_dedupe_key(payload: dict[str, Any]) -> str:
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
) -> WebhookIngestionResult:
    event_type = str(payload.get("event_type") or payload.get("type") or "")
    resource_name = resource_name_for_event_type(event_type) or ""
    sanitized_payload = redact_sensitive_fields(payload)
    raw_occurred_at = payload.get("occurred_at")
    if raw_occurred_at is not None and not isinstance(raw_occurred_at, str):
        raise ValueError("Webhook 'occurred_at' must be a string when provided.")
    occurred_at = parse_datetime(raw_occurred_at) if raw_occurred_at else None
    dedupe_key = build_webhook_dedupe_key(payload)
    event_id = str(
        payload.get("event_id") or payload.get("id") or payload.get("notification_id") or ""
    )

    if resource_name and not isinstance(payload.get("data"), dict):
        raise ValueError("Webhook resource payloads must include a JSON object in 'data'.")

    webhook_event, created = WebhookEvent.objects.update_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "event_id": event_id,
            "event_type": event_type,
            "resource_name": resource_name,
            "signature_verified": signature_verified,
            "payload": sanitized_payload,
            "headers": filter_persisted_headers(headers),
            "sync_error": "",
            "occurred_at": occurred_at,
            "processed_at": timezone.now(),
        },
    )

    synced_resource = None
    sync_error = ""
    if resource_name:
        resource_payload = dict(payload["data"])
        if not any(resource_payload.get(key) for key in RESOURCE_ORDERING_KEYS) and payload.get(
            "occurred_at"
        ):
            resource_payload["occurred_at"] = payload["occurred_at"]

        try:
            synced_resource = sync_payload(resource_name, resource_payload, source="webhook")
        except Exception as exc:
            sync_error = str(exc)
            webhook_event.sync_error = sync_error
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["sync_error", "processed_at", "updated_at"])
        else:
            webhook_event.sync_error = ""
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["sync_error", "processed_at", "updated_at"])

    return WebhookIngestionResult(
        webhook_event=webhook_event,
        synced_resource=synced_resource,
        created=created,
        sync_error=sync_error,
    )
