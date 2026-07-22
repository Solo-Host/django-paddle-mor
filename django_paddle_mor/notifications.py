from __future__ import annotations

import json
from typing import Any

from django.core.mail import EmailMessage

from .permission_validation import (
    API_KEY_PERMISSION_EVENT_TYPES,
    PermissionValidationResult,
    get_configured_api_key_entity_id,
    validate_api_key_permissions_payload,
)
from .signals import webhook_pre_process

SUPPORTED_API_KEY_NOTIFICATION_EVENTS = frozenset(
    {
        "api_key.created",
        "api_key.updated",
        "api_key.expiring",
        "api_key.expired",
        "api_key.revoked",
        "api_key_exposure.created",
    }
)


def _render_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _extract_payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    payload_data = payload.get("data")
    return payload_data if isinstance(payload_data, dict) else {}


def _api_key_label(payload: dict[str, Any], event_type: str) -> str:
    payload_data = _extract_payload_data(payload)
    raw_name = payload_data.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()

    raw_identifier = payload_data.get("id") or payload_data.get("api_key_id")
    if isinstance(raw_identifier, str) and raw_identifier.strip():
        return raw_identifier.strip()

    return event_type


def _build_validation_section(result: PermissionValidationResult) -> list[str]:
    lines = [
        "Permission validation",
        "---------------------",
        f"Expected permissions: {', '.join(result.expected_permissions) or '(none)'}",
        f"Actual permissions: {', '.join(result.actual_permissions) or '(none)'}",
    ]
    if result.matches_configured_key is not None:
        lines.append(
            f"Matches configured API key: {'yes' if result.matches_configured_key else 'no'}"
        )
    if result.has_mismatch:
        lines.append(f"Missing permissions: {', '.join(result.missing_permissions) or '(none)'}")
        lines.append(f"Extra permissions: {', '.join(result.extra_permissions) or '(none)'}")
    else:
        lines.append("Permissions match the configured manifest.")
    return lines


def _build_email_subject(
    event_type: str,
    payload: dict[str, Any],
    *,
    validation_result: PermissionValidationResult | None = None,
    mismatch_only: bool = False,
) -> str:
    label = _api_key_label(payload, event_type)
    if mismatch_only and validation_result is not None:
        return (
            "[django-paddle-mor] Paddle API key permissions mismatch: "
            f"{label} ({validation_result.api_key_id})"
        )

    subject = f"[django-paddle-mor] Paddle webhook: {event_type} - {label}"
    if validation_result is not None and validation_result.has_mismatch:
        subject += " (permissions mismatch)"
    return subject


def _build_email_body(
    webhook_event,
    *,
    validation_result: PermissionValidationResult | None = None,
) -> str:
    payload = webhook_event.payload if isinstance(webhook_event.payload, dict) else {}
    payload_data = _extract_payload_data(payload)
    lines = [
        "Paddle webhook notification",
        "===========================",
        f"Event type: {webhook_event.event_type or '(unknown)'}",
        f"Event id: {webhook_event.event_id or webhook_event.dedupe_key}",
    ]
    if webhook_event.occurred_at is not None:
        lines.append(f"Occurred at: {webhook_event.occurred_at.isoformat()}")
    if webhook_event.endpoint is not None:
        lines.append(f"Webhook endpoint: {webhook_event.endpoint}")

    if validation_result is not None:
        lines.extend(
            [
                f"API key id: {validation_result.api_key_id}",
                f"API key name: {validation_result.api_key_name}",
                f"API key status: {validation_result.key_status or '(unknown)'}",
                "",
            ]
        )
        lines.extend(_build_validation_section(validation_result))
    else:
        key_id = payload_data.get("id") or payload_data.get("api_key_id")
        key_name = payload_data.get("name")
        key_status = payload_data.get("status")
        obfuscated_key = payload_data.get("key")
        if isinstance(key_id, str) and key_id:
            lines.append(f"API key id: {key_id}")
        if isinstance(key_name, str) and key_name:
            lines.append(f"API key name: {key_name}")
        if isinstance(key_status, str) and key_status:
            lines.append(f"API key status: {key_status}")
        if isinstance(obfuscated_key, str) and obfuscated_key:
            lines.append(f"Obfuscated key: {obfuscated_key}")

    lines.extend(["", "Payload data", "------------", _render_json(payload_data or payload)])
    return "\n".join(lines)


def _send_email(subject: str, body: str, recipients: tuple[str, ...]) -> None:
    EmailMessage(subject=subject, body=body, to=list(recipients)).send(fail_silently=False)


def _handle_api_key_webhook_notifications(sender, **kwargs):
    webhook_event = kwargs["webhook_event"]
    event_type = webhook_event.event_type
    if event_type not in SUPPORTED_API_KEY_NOTIFICATION_EVENTS:
        return

    from .settings import get_django_paddle_mor_settings

    package_settings = get_django_paddle_mor_settings()
    notification_settings = package_settings.api_key_notifications
    if not notification_settings.any_enabled():
        return

    lifecycle_enabled = notification_settings.enabled_for_event(event_type)
    should_validate_permissions = (
        event_type in API_KEY_PERMISSION_EVENT_TYPES and notification_settings.permission_mismatch
    )
    if not lifecycle_enabled and not should_validate_permissions:
        return

    validation_result = None
    if should_validate_permissions:
        validation_result = validate_api_key_permissions_payload(
            webhook_event.payload,
            configured_api_key_id=get_configured_api_key_entity_id(),
        )

    recipients = package_settings.api_key_notification_recipients
    if validation_result is not None and validation_result.has_mismatch:
        subject = _build_email_subject(
            event_type,
            webhook_event.payload,
            validation_result=validation_result,
            mismatch_only=not lifecycle_enabled,
        )
        body = _build_email_body(webhook_event, validation_result=validation_result)
        _send_email(subject, body, recipients)
        return

    if lifecycle_enabled:
        subject = _build_email_subject(
            event_type,
            webhook_event.payload,
            validation_result=validation_result,
        )
        body = _build_email_body(webhook_event, validation_result=validation_result)
        _send_email(subject, body, recipients)


def register_signal_handlers() -> None:
    webhook_pre_process.connect(
        _handle_api_key_webhook_notifications,
        dispatch_uid="django_paddle_mor.api_key_webhook_notifications",
    )
