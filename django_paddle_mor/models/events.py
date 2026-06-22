from __future__ import annotations

from uuid import uuid4

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel


class WebhookEndpoint(TimeStampedModel):
    uuid = models.UUIDField(default=uuid4, unique=True, editable=False, db_index=True)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    secret = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    livemode = models.BooleanField(default=False)
    notification_setting_id = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("label", "uuid")

    def __str__(self) -> str:
        return self.label or str(self.uuid)

    def verification_secrets(self) -> tuple[str, ...]:
        normalized = self.secret.strip()
        return (normalized,) if normalized else ()


class WebhookEvent(TimeStampedModel):
    class ProcessingState(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    dedupe_key = models.CharField(max_length=255, unique=True)
    dedupe_scope = models.CharField(max_length=64, default="global")
    event_id = models.CharField(max_length=128, blank=True, db_index=True)
    event_type = models.CharField(max_length=128, blank=True)
    resource_name = models.CharField(max_length=64, blank=True)
    signature_verified = models.BooleanField(default=False)
    processing_state = models.CharField(
        max_length=16,
        choices=ProcessingState.choices,
        default=ProcessingState.PENDING,
    )
    processing_attempts = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    sync_error = models.TextField(blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(default=timezone.now)
    last_error_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-processed_at", "-created_at")

    def __str__(self) -> str:
        return self.event_id or self.dedupe_key
