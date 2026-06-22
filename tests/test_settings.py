import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from django_paddle_mor.settings import get_django_paddle_mor_settings


def test_package_settings_are_loaded_from_django_settings():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.api_key == "pdl_sandbox_test"
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
        "API_KEY": "pdl_live_test",
        "WEBHOOK_SECRETS": ["whsec_test"],
        "SANDBOX": "false",
    }
)
def test_sandbox_false_string_is_parsed_as_false():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.sandbox is False


@override_settings(DJANGO_PADDLE_MOR={"API_KEY": "pdl_live_test", "WEBHOOK_SECRETS": [None]})
def test_webhook_secrets_must_contain_strings():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()


@override_settings(
    DJANGO_PADDLE_MOR={"API_KEY": "pdl_live_test", "WEBHOOK_SECRETS": ["  whsec_test  "]}
)
def test_webhook_secrets_are_trimmed():
    package_settings = get_django_paddle_mor_settings()

    assert package_settings.webhook_secrets == ("whsec_test",)


@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": "pdl_live_test",
        "WEBHOOK_SECRETS": ["whsec_test"],
        "DEFAULT_SYNC_LIMIT": "abc",
    }
)
def test_numeric_settings_raise_improperly_configured_for_invalid_values():
    with pytest.raises(ImproperlyConfigured):
        get_django_paddle_mor_settings()
