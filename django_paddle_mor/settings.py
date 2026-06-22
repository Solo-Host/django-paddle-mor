from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured


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


def _coerce_required_string(value: object, setting_name: str) -> str:
    if not isinstance(value, str):
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] must be a string.")

    normalized = value.strip()
    if not normalized:
        raise ImproperlyConfigured(f"DJANGO_PADDLE_MOR['{setting_name}'] is required.")

    return normalized


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
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"DJANGO_PADDLE_MOR['{setting_name}'] must be an integer."
        ) from exc


def _coerce_float(value: object, setting_name: str) -> float:
    try:
        return float(value)
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

    return DjangoPaddleMorSettings(
        api_key=api_key,
        webhook_secrets=webhook_secrets,
        sandbox=_coerce_bool(raw_settings.get("SANDBOX", False), "SANDBOX"),
        api_version=api_version,
        retry_count=retry_count,
        timeout=timeout,
        default_sync_limit=default_sync_limit,
        maximum_time_drift=maximum_time_drift,
    )


def clear_django_paddle_mor_settings_cache() -> None:
    get_django_paddle_mor_settings.cache_clear()
