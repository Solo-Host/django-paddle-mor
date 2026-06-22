from __future__ import annotations

from typing import Any

REDACTED_VALUE = "[REDACTED]"
DEFAULT_SENSITIVE_KEYS = frozenset({"endpoint_secret_key"})


def redact_sensitive_fields(
    value: Any,
    *,
    sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS,
):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in sensitive_keys:
                sanitized[key] = REDACTED_VALUE
            else:
                sanitized[key] = redact_sensitive_fields(item, sensitive_keys=sensitive_keys)
        return sanitized

    if isinstance(value, list):
        return [redact_sensitive_fields(item, sensitive_keys=sensitive_keys) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_fields(item, sensitive_keys=sensitive_keys) for item in value)

    return value
