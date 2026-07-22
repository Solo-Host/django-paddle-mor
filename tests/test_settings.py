import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from django_paddle_mor.settings import get_django_paddle_mor_settings
from tests.paddle_test_support import MODERN_LIVE_API_KEY, MODERN_SANDBOX_API_KEY


def test_package_settings_are_loaded_from_django_settings():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.api_key == MODERN_SANDBOX_API_KEY
    assert package_settings.webhook_secrets == ("whsec_test",)
    assert package_settings.sandbox is True
    assert package_settings.default_sync_limit == 25


@override_settings(DJANGO_PADDLE_MOR={"WEBHOOK_SECRETS": ["whsec_test"]})
def test_api_key_is_required():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(DJANGO_PADDLE_MOR={"API_KEY": None, "WEBHOOK_SECRETS": ["whsec_test"]})
def test_api_key_must_be_a_non_empty_string():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_LIVE_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "SANDBOX": "false",
    }
)
def test_sandbox_false_string_is_parsed_as_false():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.sandbox is False


@override_settings(DJANGO_PADDLE_MOR={"API_KEY": MODERN_LIVE_API_KEY, "WEBHOOK_SECRETS": [None]})
def test_webhook_secrets_must_contain_strings():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(
    DJANGO_PADDLE_MOR={"API_KEY": MODERN_LIVE_API_KEY, "WEBHOOK_SECRETS": ["  whsec_test  "]}
)
def test_webhook_secrets_are_trimmed():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.webhook_secrets == ("whsec_test",)


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_LIVE_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "DEFAULT_SYNC_LIMIT": "abc",
    }
)
def test_numeric_settings_raise_improperly_configured_for_invalid_values():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "PERMISSION_MANIFEST": ["customer.read", "subscription.write"],
        "API_KEY_NOTIFICATION_RECIPIENTS": ["  alerts@example.com  "],
        "API_KEY_NOTIFICATIONS": {
            "permission_mismatch": "true",
            "created": 1,
            "api_key.revoked": False,
        },
    }
)
def test_api_key_notification_settings_are_loaded():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.permission_manifest == ("customer.read", "subscription.write")
    assert package_settings.api_key_notification_recipients == ("alerts@example.com",)
    assert package_settings.api_key_notifications.permission_mismatch is True
    assert package_settings.api_key_notifications.created is True
    assert package_settings.api_key_notifications.revoked is False


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "API_KEY_NOTIFICATIONS": {"created": True},
    }
)
def test_api_key_notifications_require_recipients():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "API_KEY_NOTIFICATION_RECIPIENTS": ["alerts@example.com"],
        "API_KEY_NOTIFICATIONS": {"permission_mismatch": True},
    }
)
def test_permission_mismatch_notifications_require_manifest():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()
