from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from .settings import get_django_paddle_mor_settings

API_KEY_PERMISSION_EVENT_TYPES = frozenset({"api_key.created", "api_key.updated"})
MODERN_API_KEY_PATTERN = re.compile(
    r"^pdl_(?:live|sdbx)_apikey_(?P<entity_id>[a-z\d]{26})_[A-Za-z\d]{22}_[A-Za-z\d]{3}$"
)
PADDLE_PERMISSION_PATTERN = re.compile(r"^[a-z_]+\.(?:read|write)$")


@dataclass(frozen=True, slots=True)
class PermissionValidationResult:
    api_key_id: str
    api_key_name: str
    key_status: str
    event_id: str
    event_type: str
    expected_permissions: tuple[str, ...]
    actual_permissions: tuple[str, ...]
    missing_permissions: tuple[str, ...]
    extra_permissions: tuple[str, ...]
    matches_configured_key: bool | None = None

    @property
    def has_mismatch(self) -> bool:
        return bool(self.missing_permissions or self.extra_permissions)


def _coerce_permission_sequence(
    value: object,
    *,
    context_name: str,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or isinstance(value, dict):
        raise ImproperlyConfigured(f"{context_name} must be a sequence of strings.")

    try:
        iterator = iter(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ImproperlyConfigured(f"{context_name} must be a sequence of strings.") from exc

    permissions = set()
    for item in iterator:
        if not isinstance(item, str):
            raise ImproperlyConfigured(f"{context_name} entries must be strings.")
        normalized = item.strip()
        if not normalized:
            raise ImproperlyConfigured(f"{context_name} entries must be non-empty strings.")
        if PADDLE_PERMISSION_PATTERN.fullmatch(normalized) is None:
            raise ImproperlyConfigured(
                f"{context_name} entry '{normalized}' must look like 'entity.read' "
                "or 'entity.write'."
            )
        permissions.add(normalized)

    return tuple(sorted(permissions))


def extract_api_key_entity_id(api_key: str) -> str:
    normalized = api_key.strip()
    match = MODERN_API_KEY_PATTERN.fullmatch(normalized)
    if match is None:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['API_KEY'] must use the modern Paddle Billing "
            "API key format."
        )
    return f"apikey_{match.group('entity_id')}"


def get_configured_api_key_entity_id() -> str:
    package_settings = get_django_paddle_mor_settings()
    return extract_api_key_entity_id(package_settings.api_key)


def load_permission_manifest() -> tuple[str, ...]:
    package_settings = get_django_paddle_mor_settings()
    manifest_source: object | None = package_settings.permission_manifest
    if manifest_source is None:
        return ()

    if isinstance(manifest_source, str):
        manifest_source = import_string(manifest_source)
        if callable(manifest_source):
            manifest_source = manifest_source()

    return _coerce_permission_sequence(
        manifest_source,
        context_name="DJANGO_PADDLE_MOR['PERMISSION_MANIFEST']",
    )


def validate_api_key_permissions_payload(
    payload: dict[str, Any],
    *,
    expected_permissions: Iterable[str] | None = None,
    configured_api_key_id: str | None = None,
) -> PermissionValidationResult:
    event_type = str(payload.get("event_type") or payload.get("type") or "")
    if event_type not in API_KEY_PERMISSION_EVENT_TYPES:
        raise ValueError(
            "Permission validation only supports 'api_key.created' and 'api_key.updated' events."
        )

    payload_data = payload.get("data")
    if not isinstance(payload_data, dict):
        raise ValueError("Paddle api_key webhook payloads must include a JSON object in 'data'.")

    raw_api_key_id = payload_data.get("id")
    if not isinstance(raw_api_key_id, str) or not raw_api_key_id.strip():
        raise ValueError("Paddle api_key webhook payloads must include a non-empty data.id.")
    api_key_id = raw_api_key_id.strip()

    raw_permissions = payload_data.get("permissions")
    if not isinstance(raw_permissions, list):
        raise ValueError("Paddle api_key webhook payloads must include data.permissions as a list.")

    actual_permissions = _coerce_permission_sequence(
        raw_permissions,
        context_name="Paddle api_key webhook payload permissions",
    )
    resolved_expected_permissions = (
        load_permission_manifest()
        if expected_permissions is None
        else _coerce_permission_sequence(
            expected_permissions,
            context_name="expected_permissions",
        )
    )

    actual_permissions_set = set(actual_permissions)
    expected_permissions_set = set(resolved_expected_permissions)
    missing_permissions = tuple(sorted(expected_permissions_set - actual_permissions_set))
    extra_permissions = tuple(sorted(actual_permissions_set - expected_permissions_set))

    raw_api_key_name = payload_data.get("name")
    api_key_name = api_key_id
    if isinstance(raw_api_key_name, str) and raw_api_key_name.strip():
        api_key_name = raw_api_key_name.strip()

    key_status = str(payload_data.get("status") or "").strip()
    event_id = str(payload.get("event_id") or payload.get("notification_id") or "").strip()
    matches_configured_key = None
    if configured_api_key_id is not None:
        matches_configured_key = configured_api_key_id == api_key_id

    return PermissionValidationResult(
        api_key_id=api_key_id,
        api_key_name=api_key_name,
        key_status=key_status,
        event_id=event_id,
        event_type=event_type,
        expected_permissions=resolved_expected_permissions,
        actual_permissions=actual_permissions,
        missing_permissions=missing_permissions,
        extra_permissions=extra_permissions,
        matches_configured_key=matches_configured_key,
    )
