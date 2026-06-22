import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from django_paddle_mor.exceptions import NonPersistedResourceError
from django_paddle_mor.models import (
    Customer,
    DiscountGroup,
    EventType,
    Price,
    Product,
    Subscription,
    Transaction,
)
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


@pytest.mark.django_db
def test_customer_sync_populates_typed_fields():
    customer = sync_payload(
        "customers",
        {
            "id": "cus_123",
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "marketing_consent": True,
            "locale": "en",
            "status": "active",
            "custom_data": {"team": "founders"},
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    assert customer.email == "ada@example.com"
    assert customer.marketing_consent is True
    assert customer.locale == "en"
    assert Customer.objects.get(paddle_id="cus_123").custom_data == {"team": "founders"}


@pytest.mark.django_db
def test_product_and_price_sync_populate_typed_fields_and_relations():
    product = sync_payload(
        "products",
        {
            "id": "pro_123",
            "name": "Starter",
            "description": "Starter plan",
            "tax_category": "standard",
            "image_url": "https://example.com/product.png",
            "type": "standard",
            "custom_data": {"tier": "starter"},
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    price = sync_payload(
        "prices",
        {
            "id": "pri_123",
            "product_id": "pro_123",
            "name": "Starter monthly",
            "description": "Monthly starter price",
            "type": "standard",
            "tax_mode": "account_setting",
            "billing_cycle": {"interval": "month", "frequency": 1},
            "unit_price": {"amount": "1200", "currency_code": "USD"},
            "quantity": {"minimum": 1, "maximum": 1},
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    assert product.tax_category == "standard"
    assert price.product == product
    assert price.product_external_id == "pro_123"
    assert price.unit_price_amount == "1200"
    assert Price.objects.get(paddle_id="pri_123").unit_price_currency_code == "USD"


@pytest.mark.django_db
def test_parent_sync_backfills_out_of_order_child_relations():
    price = sync_payload(
        "prices",
        {
            "id": "pri_out_of_order",
            "product_id": "pro_out_of_order",
            "description": "Price before product",
            "unit_price": {"amount": "1200", "currency_code": "USD"},
            "quantity": {"minimum": 1, "maximum": 1},
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    assert price.product is None

    product = sync_payload(
        "products",
        {
            "id": "pro_out_of_order",
            "name": "Out of order product",
            "tax_category": "standard",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    assert Price.objects.get(paddle_id="pri_out_of_order").product == product


@pytest.mark.django_db
def test_subscription_sync_links_to_customer_and_promotes_fields():
    sync_payload(
        "customers",
        {
            "id": "cus_123",
            "email": "ada@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    subscription = sync_payload(
        "subscriptions",
        {
            "id": "sub_123",
            "customer_id": "cus_123",
            "address_id": "add_123",
            "currency_code": "USD",
            "collection_mode": "automatic",
            "billing_cycle": {"interval": "month", "frequency": 1},
            "current_billing_period": {"starts_at": "2026-01-01T00:00:00Z"},
            "management_urls": {"update_payment_method": "https://example.com/manage"},
            "items": [{"price_id": "pri_123"}],
            "status": "active",
            "started_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        },
    )

    assert subscription.customer.paddle_id == "cus_123"
    assert subscription.currency_code == "USD"
    assert subscription.collection_mode == "automatic"
    assert Subscription.objects.get(paddle_id="sub_123").items == [{"price_id": "pri_123"}]


@pytest.mark.django_db
def test_transaction_sync_links_to_customer_and_subscription():
    sync_payload(
        "customers",
        {
            "id": "cus_123",
            "email": "ada@example.com",
            "marketing_consent": False,
            "locale": "en",
            "status": "active",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    sync_payload(
        "subscriptions",
        {
            "id": "sub_123",
            "customer_id": "cus_123",
            "address_id": "add_123",
            "currency_code": "USD",
            "collection_mode": "automatic",
            "billing_cycle": {"interval": "month", "frequency": 1},
            "items": [],
            "status": "active",
            "updated_at": "2026-01-02T00:00:00Z",
        },
    )

    transaction = sync_payload(
        "transactions",
        {
            "id": "txn_123",
            "customer_id": "cus_123",
            "subscription_id": "sub_123",
            "currency_code": "USD",
            "origin": "api",
            "collection_mode": "automatic",
            "details": {"line_items_subtotal": {"amount": "1200"}},
            "items": [{"price_id": "pri_123"}],
            "payments": [],
            "checkout": {"url": "https://checkout.example/session"},
            "status": "ready",
            "updated_at": "2026-01-03T00:00:00Z",
        },
    )

    assert transaction.customer.paddle_id == "cus_123"
    assert transaction.subscription.paddle_id == "sub_123"
    assert transaction.checkout_url == "https://checkout.example/session"
    assert Transaction.objects.get(paddle_id="txn_123").origin == "api"


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
