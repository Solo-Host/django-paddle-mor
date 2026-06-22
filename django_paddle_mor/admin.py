from django.contrib import admin

from .event_handlers import reprocess_webhook_event
from .models import RESOURCE_MODELS, WebhookEndpoint, WebhookEvent


@admin.action(description="Reprocess selected webhook events")
def reprocess_selected_webhook_events(modeladmin, request, queryset):
    success_count = 0
    failure_count = 0

    for webhook_event in queryset:
        result = reprocess_webhook_event(webhook_event)
        if result.sync_error:
            failure_count += 1
        else:
            success_count += 1

    if success_count:
        modeladmin.message_user(
            request,
            f"Reprocessed {success_count} webhook event(s) successfully.",
        )
    if failure_count:
        modeladmin.message_user(
            request,
            f"{failure_count} webhook event(s) still failed during reprocessing.",
            level="warning",
        )


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("label", "uuid", "enabled", "livemode", "notification_setting_id")
    search_fields = ("label", "uuid", "notification_setting_id")
    list_filter = ("enabled", "livemode")
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    actions = [reprocess_selected_webhook_events]
    list_display = (
        "endpoint",
        "event_id",
        "event_type",
        "resource_name",
        "processing_state",
        "processing_attempts",
        "signature_verified",
        "processed_at",
    )
    search_fields = ("event_id", "event_type", "dedupe_key")
    list_filter = ("processing_state", "signature_verified", "resource_name")
    readonly_fields = (
        "endpoint",
        "processing_state",
        "processing_attempts",
        "payload",
        "headers",
        "sync_error",
        "last_error_at",
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
