from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

API_KEY_NOTIFICATION_ALIASES: Mapping[str, str] = {
    "created": "created",
    "api_key_created": "created",
    "updated": "updated",
    "api_key_updated": "updated",
    "expiring": "expiring",
    "api_key_expiring": "expiring",
    "expired": "expired",
    "api_key_expired": "expired",
    "revoked": "revoked",
    "api_key_revoked": "revoked",
    "exposure_created": "exposure_created",
    "api_key_exposure_created": "exposure_created",
    "permission_mismatch": "permission_mismatch",
}


@dataclass(frozen=True, slots=True)
class APIKeyNotificationSettings:
    created: bool
    updated: bool
    expiring: bool
    expired: bool
    revoked: bool
    exposure_created: bool
    permission_mismatch: bool

    def any_enabled(self) -> bool:
        return any(
            (
                self.created,
                self.updated,
                self.expiring,
                self.expired,
                self.revoked,
                self.exposure_created,
                self.permission_mismatch,
            )
        )

    def enabled_for_event(self, event_type: str) -> bool:
        return {
            "api_key.created": self.created,
            "api_key.updated": self.updated,
            "api_key.expiring": self.expiring,
            "api_key.expired": self.expired,
            "api_key.revoked": self.revoked,
            "api_key_exposure.created": self.exposure_created,
        }.get(event_type, False)


@dataclass(frozen=True, slots=True)
class DjangoPaddleMorSettings:
    api_key: str
    webhook_secrets: tuple[str, ...]
    sandbox: bool
    api_version: int
    retry_count: int
    timeout: float
    default_sync_limit: int
    maximum_time_drift: int
    subscriber_model: str | None
    subscriber_email_field: str
    auto_link_subscriber: bool
    permission_manifest: str | tuple[str, ...] | None
    api_key_notification_recipients: tuple[str, ...]
    api_key_notifications: APIKeyNotificationSettings


def _coerce_required_string(value: object, setting_name: str) -> str:
    if not isinstance(value, str):
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] must be a string.")

    normalized = value.strip()
    if not normalized:
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] is required.")

    return normalized


def _coerce_optional_string(value: object, setting_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] must be a string.")

    normalized = value.strip()
    return normalized or None


def _coerce_string_tuple(value: object, setting_name: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ImproperlyConfigured(
                f"DJANGO_PADDLE_MOR['{setting_name}'] entries must be non-empty strings."
            )
        return (normalized,)
    if isinstance(value, (list, tuple)):
        normalized_items = []
        for item in value:
            if not isinstance(item, str):
                raise ImproperlyConfigured(
                    f"DJANGO_PADDLE_MOR['{setting_name}'] entries must be strings."
                )
            normalized = item.strip()
            if not normalized:
                raise ImproperlyConfigured(
                    f"DJANGO_PADDLE_MOR['{setting_name}'] entries must be non-empty strings."
                )
            normalized_items.append(normalized)
        return tuple(normalized_items)
    raise ImproperlyConfigured(
        f"DJANGO_PADDLE_MOR['{setting_name}'] must be a string or sequence of strings."
    )


def _coerce_permission_manifest(
    value: object,
    setting_name: str,
) -> str | tuple[str, ...] | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] is required.")
        return normalized
    if isinstance(value, (list, tuple, set, frozenset)):
        normalized_items = []
        for item in value:
            if not isinstance(item, str):
                raise ImproperlyConfigured(
                    f"DJANGO_PADDLE_MOR['{setting_name}'] entries must be strings."
                )
            normalized = item.strip()
            if not normalized:
                raise ImproperlyConfigured(
                    f"DJANGO_PADDLE_MOR['{setting_name}'] entries must be non-empty strings."
                )
            normalized_items.append(normalized)
        return tuple(normalized_items)
    raise ImproperlyConfigured(
        f"DJANGO_PADDLE_MOR['{setting_name}'] must be a dotted import path string "
        "or sequence of strings."
    )


def _normalize_nested_setting_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(".", "_").replace(" ", "_")


def _coerce_api_key_notifications(
    value: object,
    setting_name: str,
) -> APIKeyNotificationSettings:
    if value in (None, ""):
        return APIKeyNotificationSettings(
            created=False,
            updated=False,
            expiring=False,
            expired=False,
            revoked=False,
            exposure_created=False,
            permission_mismatch=False,
        )
    if not isinstance(value, Mapping):
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] must be a dictionary.")

    flags = {
        "created": False,
        "updated": False,
        "expiring": False,
        "expired": False,
        "revoked": False,
        "exposure_created": False,
        "permission_mismatch": False,
    }
    supported = ", ".join(sorted(API_KEY_NOTIFICATION_ALIASES))
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ImproperlyConfigured(
                f"DJANGO_PADDLE_MOR['{setting_name}'] keys must be strings."
            )
        normalized_key = _normalize_nested_setting_key(raw_key)
        try:
            flag_name = API_KEY_NOTIFICATION_ALIASES[normalized_key]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"Unsupported DJANGO_PADDLE_MOR['{setting_name}'] key '{raw_key}'. "
                f"Supported values: {supported}."
            ) from exc
        flags[flag_name] = _coerce_bool(raw_value, f"{setting_name}.{raw_key}")

    return APIKeyNotificationSettings(**flags)


def _coerce_bool(value: object, setting_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    raise ImproperlyConfigured(
        f"DJANGO_PADDLE_MOR['{setting_name}'] must be a boolean or boolean-like string."
    )


def _coerce_int(value: object, setting_name: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"DJANGO_PADDLE_MOR['{setting_name}'] must be an integer."
            ) from exc
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"DJANGO_PADDLE_MOR['{setting_name}'] must be an integer."
        ) from exc


def _coerce_float(value: object, setting_name: str) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"DJANGO_PADDLE_MOR['{setting_name}'] must be a number."
            ) from exc
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"DJANGO_PADDLE_MOR['{setting_name}'] must be a number."
        ) from exc


@lru_cache(maxsize=1)
def get_django_paddle_mor_settings() -> DjangoPaddleMorSettings:
    raw_settings = getattr(django_settings, "DJANGO_PADDLE_MOR", None)
    if raw_settings is None:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR settings are required.")
    if not isinstance(raw_settings, dict):
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR must be a dictionary.")

    api_key = _coerce_required_string(raw_settings.get("API_KEY", ""), "API_KEY")

    webhook_secrets = _coerce_string_tuple(
        raw_settings.get("WEBHOOK_SECRETS", raw_settings.get("WEBHOOK_SECRET")),
        "WEBHOOK_SECRETS",
    )
    default_sync_limit = _coerce_int(
        raw_settings.get("DEFAULT_SYNC_LIMIT", 100),
        "DEFAULT_SYNC_LIMIT",
    )
    api_version = _coerce_int(raw_settings.get("API_VERSION", 1), "API_VERSION")
    retry_count = _coerce_int(raw_settings.get("RETRY_COUNT", 3), "RETRY_COUNT")
    timeout = _coerce_float(raw_settings.get("TIMEOUT", 60.0), "TIMEOUT")
    maximum_time_drift = _coerce_int(
        raw_settings.get("MAXIMUM_TIME_DRIFT", 5),
        "MAXIMUM_TIME_DRIFT",
    )
    subscriber_model = _coerce_optional_string(
        raw_settings.get("SUBSCRIBER_MODEL"),
        "SUBSCRIBER_MODEL",
    )
    subscriber_email_field = _coerce_required_string(
        raw_settings.get("SUBSCRIBER_EMAIL_FIELD", "email"),
        "SUBSCRIBER_EMAIL_FIELD",
    )
    auto_link_subscriber = _coerce_bool(
        raw_settings.get("AUTO_LINK_SUBSCRIBER", False),
        "AUTO_LINK_SUBSCRIBER",
    )
    permission_manifest = _coerce_permission_manifest(
        raw_settings.get("PERMISSION_MANIFEST"),
        "PERMISSION_MANIFEST",
    )
    api_key_notification_recipients = _coerce_string_tuple(
        raw_settings.get("API_KEY_NOTIFICATION_RECIPIENTS"),
        "API_KEY_NOTIFICATION_RECIPIENTS",
    )
    api_key_notifications = _coerce_api_key_notifications(
        raw_settings.get("API_KEY_NOTIFICATIONS"),
        "API_KEY_NOTIFICATIONS",
    )

    if default_sync_limit < 1:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR['DEFAULT_SYNC_LIMIT'] must be >= 1.")
    if api_version < 1:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR['API_VERSION'] must be >= 1.")
    if retry_count < 0:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR['RETRY_COUNT'] must be >= 0.")
    if timeout <= 0:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR['TIMEOUT'] must be > 0.")
    if maximum_time_drift < 0:
        raise ImproperlyConfigured("DJANGO_PADDLE_MOR['MAXIMUM_TIME_DRIFT'] must be >= 0.")
    if api_key_notifications.any_enabled() and not api_key_notification_recipients:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['API_KEY_NOTIFICATION_RECIPIENTS'] is required "
            "when API_KEY_NOTIFICATIONS are enabled."
        )
    if api_key_notifications.permission_mismatch and permission_manifest is None:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['PERMISSION_MANIFEST'] is required when "
            "API_KEY_NOTIFICATIONS['PERMISSION_MISMATCH'] is enabled."
        )

    return DjangoPaddleMorSettings(
        api_key=api_key,
        webhook_secrets=webhook_secrets,
        sandbox=_coerce_bool(raw_settings.get("SANDBOX", False), "SANDBOX"),
        api_version=api_version,
        retry_count=retry_count,
        timeout=timeout,
        default_sync_limit=default_sync_limit,
        maximum_time_drift=maximum_time_drift,
        subscriber_model=subscriber_model,
        subscriber_email_field=subscriber_email_field,
        auto_link_subscriber=auto_link_subscriber,
        permission_manifest=permission_manifest,
        api_key_notification_recipients=api_key_notification_recipients,
        api_key_notifications=api_key_notifications,
    )


def clear_django_paddle_mor_settings_cache() -> None:
    get_django_paddle_mor_settings.cache_clear()
