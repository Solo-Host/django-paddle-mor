import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from django_paddle_mor.exceptions import NonPersistedResourceError
from django_paddle_mor.models import DiscountGroup, EventType, Product
from django_paddle_mor.sync import (
    ZERO_ARGUMENT_LIST_RESOURCE_NAMES,
    resource_name_for_event_type,
    sync_all_resources,
    sync_payload,
    sync_resource,
)


@pytest.mark.django_db
def test_sync_payload_creates_a_product():
    product = sync_payload(
        "products",
        {
            "id": "pro_123",
            "name": "Starter",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    assert product.paddle_id == "pro_123"
    assert product.name == "Starter"
    assert Product.objects.get(paddle_id="pro_123").status == "active"


@pytest.mark.django_db
def test_sync_payload_accepts_aliases():
    discount_group = sync_payload(
        "discount-group",
        {
            "id": "dgrp_123",
            "name": "Launch Promo",
        },
    )

    assert discount_group.paddle_id == "dgrp_123"
    assert DiscountGroup.objects.filter(paddle_id="dgrp_123").exists()


def test_event_types_map_to_persisted_resource_names():
    assert resource_name_for_event_type("subscription.updated") == "subscriptions"
    assert resource_name_for_event_type("pricing_preview.created") is None


@pytest.mark.django_db
def test_stale_payloads_do_not_overwrite_newer_rows():
    sync_payload(
        "products",
        {
            "id": "pro_123",
            "name": "Newest Name",
            "updated_at": "2026-01-02T00:00:00Z",
        },
    )
    stale_result = sync_payload(
        "products",
        {
            "id": "pro_123",
            "name": "Older Name",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        source="webhook",
    )

    assert stale_result.name == "Newest Name"
    assert Product.objects.get(paddle_id="pro_123").name == "Newest Name"


@pytest.mark.django_db
def test_event_type_sync_uses_name_as_stable_identifier():
    event_type = sync_payload(
        "event_types",
        {
            "name": "transaction.paid",
            "description": "Triggered when a transaction is paid.",
            "group": "transaction",
            "available_versions": ["1"],
        },
    )

    assert event_type.paddle_id == "transaction.paid"
    assert EventType.objects.filter(paddle_id="transaction.paid").exists()


def test_sync_all_resources_uses_only_zero_argument_list_resources(monkeypatch):
    seen_resources = []

    def fake_sync_resource(resource_name, *, lookup=None, limit=None):
        assert lookup is None
        seen_resources.append(resource_name)
        return []

    monkeypatch.setattr("django_paddle_mor.sync.sync_resource", fake_sync_resource)

    sync_all_resources(limit=5)

    assert set(seen_resources) == ZERO_ARGUMENT_LIST_RESOURCE_NAMES
    assert "addresses" not in seen_resources


@pytest.mark.django_db
def test_parent_scoped_resources_can_use_lookup_to_list(monkeypatch):
    class FakeAddressesClient:
        def __init__(self):
            self.calls = []

        def list(self, customer_id):
            self.calls.append(("list", customer_id))
            return [{"id": "add_123", "name": "Home", "status": "active"}]

    fake_client = FakeAddressesClient()

    class FakePaddleAPI:
        def resource_client(self, resource_name):
            assert resource_name == "addresses"
            return fake_client

    monkeypatch.setattr("django_paddle_mor.sync.PaddleAPI", FakePaddleAPI)

    synced = sync_resource("addresses", lookup=["cus_123"], limit=10)

    assert fake_client.calls == [("list", "cus_123")]
    assert synced[0].paddle_id == "add_123"


def test_list_only_resources_reject_lookup_ids():
    with pytest.raises(ValueError, match="adjustments expected lookup identifiers"):
        sync_resource("adjustments", lookup=["adj_123"])


def test_management_command_wraps_lookup_errors():
    with pytest.raises(CommandError, match="requires 1 lookup identifier"):
        call_command("sync_paddle_resources", "addresses")


def test_sync_payload_rejects_service_only_resources():
    with pytest.raises(NonPersistedResourceError, match="pricing_previews"):
        sync_payload("pricing_previews", {"id": "preview_123"})
