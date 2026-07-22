from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.checks import run_checks
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from django_paddle_mor.models import Customer, WebhookEndpoint, WebhookEvent
from django_paddle_mor.sync import sync_payload
from tests.paddle_test_support import MODERN_SANDBOX_API_KEY


def _subscriber_settings(**overrides):
    settings = {
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": ["whsec_test"],
        "SANDBOX": True,
        "DEFAULT_SYNC_LIMIT": 25,
        "SUBSCRIBER_MODEL": "auth.User",
        "SUBSCRIBER_EMAIL_FIELD": "email",
    }
    settings.update(overrides)
    return settings


@pytest.mark.django_db
@override_settings(DJANGO_PADDLE_MOR=_subscriber_settings(AUTO_LINK_SUBSCRIBER=True))
def test_customer_sync_auto_links_to_subscriber():
    user = get_user_model().objects.create_user(username="ada", email="ada@example.com")

    customer = sync_payload(
        "customers",
        {
            "id": "cus_auto_link",
            "email": "ada@example.com",
            "marketing_consent": True,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    assert customer.subscriber == user


@pytest.mark.django_db
@override_settings(DJANGO_PADDLE_MOR=_subscriber_settings())
def test_link_paddle_customers_command_links_existing_customers():
    user = get_user_model().objects.create_user(username="grace", email="grace@example.com")
    sync_payload(
        "customers",
        {
            "id": "cus_link_cmd",
            "email": "grace@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    stdout = StringIO()
    call_command("link_paddle_customers", stdout=stdout)

    customer = Customer.objects.get(paddle_id="cus_link_cmd")
    assert customer.subscriber == user
    assert "Linked 1 of 1 inspected customer(s)." in stdout.getvalue()


@pytest.mark.django_db
@override_settings(DJANGO_PADDLE_MOR=_subscriber_settings())
def test_link_paddle_customers_command_repairs_stale_links():
    old_user = get_user_model().objects.create_user(username="old", email="stale@example.com")
    customer = sync_payload(
        "customers",
        {
            "id": "cus_stale_link",
            "email": "stale@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    customer.link_subscriber(old_user)
    old_user.delete()

    new_user = get_user_model().objects.create_user(username="new", email="stale@example.com")
    stdout = StringIO()
    call_command("link_paddle_customers", stdout=stdout)

    customer.refresh_from_db()
    assert customer.subscriber == new_user
    assert "Linked 1 of 1 inspected customer(s)." in stdout.getvalue()


@pytest.mark.django_db
@override_settings(DJANGO_PADDLE_MOR=_subscriber_settings(AUTO_LINK_SUBSCRIBER=True))
def test_customer_auto_link_retargets_when_email_changes():
    old_user = get_user_model().objects.create_user(username="old", email="old@example.com")
    new_user = get_user_model().objects.create_user(username="new", email="new@example.com")

    customer = sync_payload(
        "customers",
        {
            "id": "cus_email_retarget",
            "email": "old@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    assert customer.subscriber == old_user

    updated_customer = sync_payload(
        "customers",
        {
            "id": "cus_email_retarget",
            "email": "new@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-02T00:00:00Z",
        },
    )

    assert updated_customer.subscriber == new_user


@pytest.mark.django_db
def test_clear_paddle_webhook_events_dry_run_reports_matches():
    WebhookEvent.objects.create(
        dedupe_key="event:global:evt_old",
        event_id="evt_old",
        processing_state=WebhookEvent.ProcessingState.PROCESSED,
        processed_at=timezone.now() - timedelta(days=31),
    )

    stdout = StringIO()
    call_command("clear_paddle_webhook_events", "--dry-run", stdout=stdout)

    assert "1 webhook event(s) would be deleted." in stdout.getvalue()
    assert WebhookEvent.objects.filter(event_id="evt_old").exists()


@override_settings(
    DJANGO_PADDLE_MOR=_subscriber_settings(
        AUTO_LINK_SUBSCRIBER=True,
        SUBSCRIBER_MODEL=None,
    )
)
def test_system_checks_warn_when_auto_link_has_no_subscriber_model():
    messages = run_checks(tags=["django_paddle_mor"])

    assert any(message.id == "django_paddle_mor.W001" for message in messages)


@pytest.mark.django_db
@override_settings(
    DJANGO_PADDLE_MOR={
        "API_KEY": MODERN_SANDBOX_API_KEY,
        "WEBHOOK_SECRETS": [],
        "SANDBOX": True,
    }
)
def test_system_checks_warn_when_enabled_endpoint_has_no_secret_and_no_global_secret():
    WebhookEndpoint.objects.create(label="Blank secret endpoint", secret="", enabled=True)

    messages = run_checks(tags=["django_paddle_mor"])

    assert any(message.id == "django_paddle_mor.W002" for message in messages)
