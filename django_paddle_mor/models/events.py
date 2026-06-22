from __future__ import annotations

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel


class WebhookEvent(TimeStampedModel):
    dedupe_key = models.CharField(max_length=128, unique=True)
    event_id = models.CharField(max_length=128, blank=True, db_index=True)
    event_type = models.CharField(max_length=128, blank=True)
    resource_name = models.CharField(max_length=64, blank=True)
    signature_verified = models.BooleanField(default=False)
    payload = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    sync_error = models.TextField(blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-processed_at", "-created_at")

    def __str__(self) -> str:
        return self.event_id or self.dedupe_key
