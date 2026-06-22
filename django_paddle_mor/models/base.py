from __future__ import annotations

from typing import Any, ClassVar

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from django_paddle_mor.exceptions import MissingPaddleIdentifierError
from django_paddle_mor.sanitization import redact_sensitive_fields

COMMON_EFFECTIVE_AT_KEYS = (
    "effective_at",
    "occurred_at",
    "updated_at",
    "created_at",
    "generated_at",
    "started_at",
)
COMMON_NAME_KEYS = ("name", "title", "label", "description")


def _coerce_datetime(value: object) -> object:
    if not isinstance(value, str):
        return None
    return parse_datetime(value)


def _extract_first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_first_datetime(payload: dict[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        parsed = _coerce_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    return None


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AbstractPaddleResource(TimeStampedModel):
    RESOURCE_NAME: ClassVar[str]
    EVENT_PREFIXES: ClassVar[tuple[str, ...]] = ()

    paddle_id = models.CharField(max_length=128, unique=True)
    resource_type = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    effective_at = models.DateTimeField(null=True, blank=True)
    remote_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_from = models.CharField(max_length=32, default="api")
    synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True
        ordering = ("-synced_at", "paddle_id")

    def __str__(self) -> str:
        return self.name or self.paddle_id

    def save(self, *args, **kwargs):
        if not self.resource_type:
            self.resource_type = self.RESOURCE_NAME
        super().save(*args, **kwargs)

    @classmethod
    def extract_paddle_id(cls, payload: dict[str, Any]) -> str:
        identifier = payload.get("id")
        if not identifier:
            raise MissingPaddleIdentifierError(
                f"{cls.__name__} payload is missing the 'id' field required for synchronization."
            )
        return str(identifier)

    @classmethod
    def defaults_from_payload(cls, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        return {
            "resource_type": cls.RESOURCE_NAME,
            "status": str(payload.get("status", "") or ""),
            "name": _extract_first_string(payload, COMMON_NAME_KEYS),
            "payload": redact_sensitive_fields(payload),
            "occurred_at": _coerce_datetime(payload.get("occurred_at")),
            "effective_at": _extract_first_datetime(payload, COMMON_EFFECTIVE_AT_KEYS),
            "remote_updated_at": _coerce_datetime(payload.get("updated_at")),
            "last_synced_from": source,
            "synced_at": timezone.now(),
        }

    @classmethod
    def should_apply_update(
        cls,
        instance: AbstractPaddleResource,
        defaults: dict[str, Any],
    ) -> bool:
        incoming_ordering_value = (
            defaults.get("remote_updated_at")
            or defaults.get("effective_at")
            or defaults.get("occurred_at")
        )
        current_ordering_value = (
            instance.remote_updated_at or instance.effective_at or instance.occurred_at
        )

        if current_ordering_value is not None and incoming_ordering_value is None:
            return False

        if incoming_ordering_value is None or current_ordering_value is None:
            return True

        return incoming_ordering_value >= current_ordering_value

    @classmethod
    def sync_from_payload(cls, payload: dict[str, Any], *, source: str = "api"):
        paddle_id = cls.extract_paddle_id(payload)
        defaults = cls.defaults_from_payload(payload, source=source)

        with transaction.atomic():
            try:
                instance = cls.objects.select_for_update().get(paddle_id=paddle_id)
            except cls.DoesNotExist:
                try:
                    with transaction.atomic():
                        return cls.objects.create(paddle_id=paddle_id, **defaults)
                except IntegrityError:
                    instance = cls.objects.select_for_update().get(paddle_id=paddle_id)

            if not cls.should_apply_update(instance, defaults):
                return instance

            for field_name, field_value in defaults.items():
                setattr(instance, field_name, field_value)
            instance.save(update_fields=[*defaults.keys(), "updated_at"])
            return instance
