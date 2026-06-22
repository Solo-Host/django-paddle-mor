from django.contrib import admin

from .models import RESOURCE_MODELS, WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "event_type",
        "resource_name",
        "signature_verified",
        "processed_at",
    )
    search_fields = ("event_id", "event_type", "dedupe_key")
    readonly_fields = (
        "payload",
        "headers",
        "sync_error",
        "processed_at",
        "created_at",
        "updated_at",
    )


class PaddleResourceAdmin(admin.ModelAdmin):
    list_display = ("paddle_id", "name", "status", "resource_type", "synced_at")
    search_fields = ("paddle_id", "name", "status")
    readonly_fields = (
        "resource_type",
        "payload",
        "occurred_at",
        "effective_at",
        "remote_updated_at",
        "synced_at",
        "created_at",
        "updated_at",
    )


for resource_model in RESOURCE_MODELS:
    admin.site.register(resource_model, PaddleResourceAdmin)
