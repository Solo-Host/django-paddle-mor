from __future__ import annotations

import pytest
from django.core import mail
from django.test import override_settings

from django_paddle_mor.event_handlers import ingest_webhook_payload
from tests.paddle_test_support import (
    DEFAULT_PERMISSION_MANIFEST,
    MODERN_API_KEY_RECORD_ID,
    MODERN_SANDBOX_API_KEY,
    OBFUSCATED_SANDBOX_API_KEY,
)


def _notification_settings(**overrides):
    settings = {
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "SANDBOX": True,
        "PERMISSION_MANIFEST": DEFAULT_PERMISSION_MANIFEST,
        "API_KEY_NOTIFICATION_RECIPIENTS": ["billing-alerts@example.com"],
        "API_KEY_NOTIFICATIONS": {},
    }
    settings.update(overrides)
    return settings


def _api_key_payload(event_type: str, *, permissions: list[str], status: str = "active") -> dict:
    return {
        "event_id": f"evt_{event_type.replace('.', '_')}",
        "event_type": event_type,
        "occurred_at": "2026-01-01T00:00:00Z",
        "data": {
            "id": MODERN_API_KEY_RECORD_ID,
            "name": "Backend API key",
            "description": "Primary billing integration",
            "key": OBFUSCATED_SANDBOX_API_KEY,
            "status": status,
            "permissions": permissions,
        },
    }


def _api_key_exposure_payload() -> dict:
    return {
        "event_id": "evt_api_key_exposure_created",
        "event_type": "api_key_exposure.created",
        "occurred_at": "2026-01-01T00:00:00Z",
        "data": {
            "id": "akexp_01gtgztp8f4kek3yd4g1wrksa3",
            "api_key_id": MODERN_API_KEY_RECORD_ID,
            "key": OBFUSCATED_SANDBOX_API_KEY,
            "public_url": "https://example.test/leak",
        },
    }


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DJANGO_PADDLE_MOR=_notification_settings(
        API_KEY_NOTIFICATIONS={"permission_mismatch": True}
    ),
)
@pytest.mark.django_db
def test_permission_mismatch_email_is_sent_for_api_key_created():
    ingest_webhook_payload(
        _api_key_payload(
            "api_key.created",
            permissions=["customer.read", "subscription.read", "product.read"],
        )
    )

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["billing-alerts@example.com"]
    assert "permissions mismatch" in message.subject.lower()
    assert "Missing permissions: subscription.write" in message.body
    assert "Extra permissions: product.read" in message.body


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DJANGO_PADDLE_MOR=_notification_settings(
        API_KEY_NOTIFICATIONS={"created": True, "permission_mismatch": True}
    ),
)
@pytest.mark.django_db
def test_created_notification_includes_matching_permission_summary():
    ingest_webhook_payload(
        _api_key_payload(
            "api_key.created",
            permissions=list(DEFAULT_PERMISSION_MANIFEST),
        )
    )

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert "api_key.created" in message.subject
    assert "Permissions match the configured manifest." in message.body


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DJANGO_PADDLE_MOR=_notification_settings(
        API_KEY_NOTIFICATIONS={"permission_mismatch": True}
    ),
)
@pytest.mark.django_db
def test_matching_permissions_do_not_send_mismatch_email():
    ingest_webhook_payload(
        _api_key_payload(
            "api_key.updated",
            permissions=list(DEFAULT_PERMISSION_MANIFEST),
        )
    )

    assert mail.outbox == []


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DJANGO_PADDLE_MOR=_notification_settings(
        API_KEY_NOTIFICATIONS={"revoked": True}
    ),
)
@pytest.mark.django_db
def test_revoked_notification_is_sent_when_enabled():
    ingest_webhook_payload(
        _api_key_payload(
            "api_key.revoked",
            permissions=list(DEFAULT_PERMISSION_MANIFEST),
            status="revoked",
        )
    )

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert "api_key.revoked" in message.subject
    assert "API key status: revoked" in message.body


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DJANGO_PADDLE_MOR=_notification_settings(
        API_KEY_NOTIFICATIONS={"api_key_exposure_created": True}
    ),
)
@pytest.mark.django_db
def test_api_key_exposure_notification_is_sent_when_enabled():
    ingest_webhook_payload(_api_key_exposure_payload())

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert "api_key_exposure.created" in message.subject
    assert "akexp_01gtgztp8f4kek3yd4g1wrksa3" in message.body
