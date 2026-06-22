from types import SimpleNamespace

import pytest
from paddle_billing.Entities.PricingPreviews import PricePreviewItem
from paddle_billing.Resources.ClientTokens.Operations import CreateClientToken
from paddle_billing.Resources.PricingPreviews.Operations import PreviewPrice
from paddle_billing.Resources.Transactions.Operations import CreateTransaction
from paddle_billing.Resources.Transactions.Operations.Create import TransactionCreateItem

from django_paddle_mor.client import PaddleAPI
from django_paddle_mor.helpers import CheckoutHelpers, PortalHelpers, SessionHelpers


def test_paddle_api_exposes_helper_namespaces():
    fake_client = object()
    api = PaddleAPI(client=fake_client)

    assert isinstance(api.checkout, CheckoutHelpers)
    assert isinstance(api.sessions, SessionHelpers)
    assert isinstance(api.portal, PortalHelpers)
    assert api.checkout.client is fake_client
    assert api.sessions.client is fake_client
    assert api.portal.client is fake_client


def test_session_helpers_manage_client_tokens():
    operations = {}
    sentinel_client_token = SimpleNamespace(id="ctk_123", token="token_123")

    class FakeClientTokens:
        def create(self, operation):
            operations["create"] = operation
            return sentinel_client_token

        def list(self, operation=None):
            operations["list"] = operation
            return ["listed"]

        def get(self, client_token_id):
            operations["get"] = client_token_id
            return sentinel_client_token

        def revoke(self, client_token_id):
            operations["revoke"] = client_token_id
            return sentinel_client_token

    helper = SessionHelpers(SimpleNamespace(client_tokens=FakeClientTokens()))

    created = helper.create_client_token("Website checkout", description="Checkout token")
    listed = helper.list_client_tokens()
    fetched = helper.get_client_token("ctk_123")
    revoked = helper.revoke_client_token("ctk_123")

    assert isinstance(operations["create"], CreateClientToken)
    assert operations["create"].name == "Website checkout"
    assert operations["create"].description == "Checkout token"
    assert listed == ["listed"]
    assert fetched is sentinel_client_token
    assert revoked is sentinel_client_token
    assert created is sentinel_client_token
    assert operations["get"] == "ctk_123"
    assert operations["revoke"] == "ctk_123"


def test_portal_helpers_create_sessions_and_urls():
    captured = {}
    portal_session = SimpleNamespace(
        urls=SimpleNamespace(
            general=SimpleNamespace(overview="https://portal.example/overview"),
            subscriptions=[
                SimpleNamespace(
                    id="sub_123",
                    cancel_subscription="https://portal.example/sub_123/cancel",
                    update_subscription_payment_method="https://portal.example/sub_123/payment-method",
                )
            ],
        )
    )

    class FakePortalSessions:
        def create(self, customer_id, operation):
            captured["customer_id"] = customer_id
            captured["operation"] = operation
            return portal_session

    helper = PortalHelpers(
        SimpleNamespace(customer_portal_sessions=FakePortalSessions())
    )

    created = helper.create_portal_session("cus_123", subscription_ids=["sub_123"])
    first_operation = captured["operation"]
    overview_url = helper.overview_url("cus_123")
    subscription_urls = helper.subscription_urls("cus_123")

    assert created is portal_session
    assert captured["customer_id"] == "cus_123"
    assert first_operation.subscription_ids == ["sub_123"]
    assert overview_url == "https://portal.example/overview"
    assert subscription_urls["sub_123"].cancel_subscription.endswith("/cancel")


def test_portal_helpers_accept_single_subscription_id_strings():
    captured = {}

    class FakePortalSessions:
        def create(self, customer_id, operation):
            captured["customer_id"] = customer_id
            captured["operation"] = operation
            return SimpleNamespace(
                urls=SimpleNamespace(
                    general=SimpleNamespace(overview="https://portal.example/overview"),
                    subscriptions=[],
                )
            )

    helper = PortalHelpers(
        SimpleNamespace(customer_portal_sessions=FakePortalSessions())
    )

    helper.create_portal_session("cus_123", subscription_ids="sub_123")

    assert captured["operation"].subscription_ids == ["sub_123"]


def test_portal_helpers_reject_conflicting_arguments():
    helper = PortalHelpers(SimpleNamespace(customer_portal_sessions=object()))

    with pytest.raises(ValueError, match="either subscription_ids or operation"):
        helper.create_portal_session(
            "cus_123",
            subscription_ids=["sub_123"],
            operation=object(),
        )


def test_checkout_helpers_prepare_checkout_session():
    captured = {}
    transaction = SimpleNamespace(id="txn_123", checkout=SimpleNamespace(url="https://checkout.example"))
    client_token = SimpleNamespace(id="ctk_123", token="token_123")
    price_preview = SimpleNamespace(details="preview")

    class FakeTransactions:
        def create(self, operation, includes=None):
            captured["transaction_operation"] = operation
            captured["transaction_includes"] = includes
            return transaction

    class FakeClientTokens:
        def create(self, operation):
            captured["client_token_operation"] = operation
            return client_token

    class FakePricingPreviews:
        def preview_prices(self, operation):
            captured["pricing_preview_operation"] = operation
            return price_preview

    helper = CheckoutHelpers(
        SimpleNamespace(
            transactions=FakeTransactions(),
            client_tokens=FakeClientTokens(),
            pricing_previews=FakePricingPreviews(),
        )
    )

    checkout_session = helper.create_checkout_session(
        CreateTransaction(items=[TransactionCreateItem(price_id="pri_123", quantity=1)]),
        client_token="Website checkout",
        client_token_description="Frontend checkout token",
        pricing_preview_operation=PreviewPrice(
            items=[PricePreviewItem(price_id="pri_123", quantity=1)]
        ),
    )

    assert checkout_session.transaction is transaction
    assert checkout_session.client_token is client_token
    assert checkout_session.pricing_preview is price_preview
    assert checkout_session.url == "https://checkout.example"
    assert isinstance(captured["client_token_operation"], CreateClientToken)
    assert captured["client_token_operation"].name == "Website checkout"
    assert captured["transaction_operation"].items[0].price_id == "pri_123"
    assert isinstance(captured["pricing_preview_operation"], PreviewPrice)


def test_checkout_helpers_revoke_client_token_if_transaction_creation_fails():
    captured = {}
    created_token = SimpleNamespace(id="ctk_123")

    class FakeTransactions:
        def create(self, operation, includes=None):
            raise RuntimeError("transaction create failed")

    class FakeClientTokens:
        def create(self, operation):
            captured["client_token_operation"] = operation
            return created_token

        def revoke(self, client_token_id):
            captured["revoked_token_id"] = client_token_id
            return created_token

    helper = CheckoutHelpers(
        SimpleNamespace(
            transactions=FakeTransactions(),
            client_tokens=FakeClientTokens(),
            pricing_previews=SimpleNamespace(preview_prices=lambda operation: None),
        )
    )

    with pytest.raises(RuntimeError, match="transaction create failed"):
        helper.create_checkout_session(
            CreateTransaction(items=[TransactionCreateItem(price_id="pri_123", quantity=1)]),
            client_token="Website checkout",
        )

    assert captured["revoked_token_id"] == "ctk_123"
