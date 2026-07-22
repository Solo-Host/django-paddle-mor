from __future__ import annotations

from django.test import override_settings

from django_paddle_mor.permission_validation import (
    extract_api_key_entity_id,
    load_permission_manifest,
    validate_api_key_permissions_payload,
)
from tests.paddle_test_support import (
    DEFAULT_PERMISSION_MANIFEST,
    MODERN_API_KEY_RECORD_ID,
    MODERN_SANDBOX_API_KEY,
    OBFUSCATED_SANDBOX_API_KEY,
)


def _validation_settings(**overrides):
    settings = {
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "SANDBOX": True,
    }
    settings.update(overrides)
    return settings


def _api_key_payload(event_type: str, *, permissions: list[str]) -> dict:
    return {
        "event_id": f"evt_{event_type.replace('.', '_')}",
        "event_type": event_type,
        "occurred_at": "2026-01-01T00:00:00Z",
        "data": {
            "id": MODERN_API_KEY_RECORD_ID,
            "name": "Backend API key",
            "description": "Primary billing integration",
            "key": OBFUSCATED_SANDBOX_API_KEY,
            "status": "active",
            "permissions": permissions,
        },
    }


def test_extract_api_key_entity_id_from_modern_key():
    assert extract_api_key_entity_id(MODERN_SANDBOX_API_KEY) == MODERN_API_KEY_RECORD_ID


@override_settings(
    DJANGO_PADDLE_MOR=_validation_settings(
        PERMISSION_MANIFEST="tests.paddle_test_support.permission_manifest"
    )
)
def test_load_permission_manifest_from_dotted_path():
    assert load_permission_manifest() == DEFAULT_PERMISSION_MANIFEST


def test_validate_api_key_permissions_payload_reports_missing_and_extra():
    result = validate_api_key_permissions_payload(
        _api_key_payload(
            "api_key.updated",
            permissions=["customer.read", "product.read", "subscription.read"],
        ),
        expected_permissions=DEFAULT_PERMISSION_MANIFEST,
        configured_api_key_id=MODERN_API_KEY_RECORD_ID,
    )

    assert result.matches_configured_key is True
    assert result.missing_permissions == ("subscription.write",)
    assert result.extra_permissions == ("product.read",)
