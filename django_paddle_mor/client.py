from __future__ import annotations

from paddle_billing.Client import Client
from paddle_billing.Environment import Environment
from paddle_billing.Notifications.Secret import Secret
from paddle_billing.Notifications.Verifier import Verifier
from paddle_billing.Options import Options

from .exceptions import WebhookVerificationError
from .registry import resolve_resource_name
from .settings import get_django_paddle_mor_settings


def build_paddle_sdk_client() -> Client:
    package_settings = get_django_paddle_mor_settings()
    environment = Environment.SANDBOX if package_settings.sandbox else Environment.PRODUCTION

    return Client(
        package_settings.api_key,
        options=Options(environment=environment, retries=package_settings.retry_count),
        retry_count=package_settings.retry_count,
        timeout=package_settings.timeout,
        use_api_version=package_settings.api_version,
    )


class PaddleAPI:
    def __init__(self, client: Client | None = None):
        self.client = client or build_paddle_sdk_client()

    def resource_client(self, resource_name: str):
        canonical_name = resolve_resource_name(resource_name)
        return getattr(self.client, canonical_name)

    def verify_webhook(self, request, *, verify_time_drift: bool = True) -> bool:
        package_settings = get_django_paddle_mor_settings()
        if not package_settings.webhook_secrets:
            raise WebhookVerificationError(
                "DJANGO_PADDLE_MOR['WEBHOOK_SECRETS'] must be configured "
                "to verify webhook requests."
            )

        verifier = Verifier(package_settings.maximum_time_drift)
        secrets = [Secret(secret) for secret in package_settings.webhook_secrets]
        try:
            return verifier.verify(request, secrets, verify_time_drift=verify_time_drift)
        except (ConnectionRefusedError, ValueError):
            return False
