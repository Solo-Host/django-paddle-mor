from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db.utils import DatabaseError

from .models import WebhookEndpoint
from .settings import get_django_paddle_mor_settings
from .subscriber import validate_subscriber_model_configuration


@checks.register("django_paddle_mor")
def check_subscriber_model_configuration(app_configs=None, **kwargs):
    messages = []
    try:
        settings = get_django_paddle_mor_settings()
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), id="django_paddle_mor.E001")]

    if settings.auto_link_subscriber and not settings.subscriber_model:
        messages.append(
            checks.Warning(
                "AUTO_LINK_SUBSCRIBER is enabled but SUBSCRIBER_MODEL is not configured.",
                hint="Set DJANGO_PADDLE_MOR['SUBSCRIBER_MODEL'] or disable AUTO_LINK_SUBSCRIBER.",
                id="django_paddle_mor.W001",
            )
        )
        return messages

    try:
        validate_subscriber_model_configuration()
    except ImproperlyConfigured as exc:
        messages.append(
            checks.Error(
                str(exc),
                id="django_paddle_mor.E002",
            )
        )

    return messages


@checks.register("django_paddle_mor")
def check_webhook_endpoint_secrets(app_configs=None, **kwargs):
    messages = []
    try:
        settings = get_django_paddle_mor_settings()
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), id="django_paddle_mor.E003")]

    try:
        has_blank_enabled_endpoints = WebhookEndpoint.objects.filter(
            enabled=True,
            secret="",
        ).exists()
    except (DatabaseError, RuntimeError):
        return []

    if has_blank_enabled_endpoints and not settings.webhook_secrets:
        messages.append(
            checks.Warning(
                "Enabled WebhookEndpoint records exist without endpoint secrets "
                "or global WEBHOOK_SECRETS.",
                hint="Populate WebhookEndpoint.secret or DJANGO_PADDLE_MOR['WEBHOOK_SECRETS'].",
                id="django_paddle_mor.W002",
            )
        )

    return messages
