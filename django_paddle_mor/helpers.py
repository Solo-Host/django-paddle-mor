from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from paddle_billing.Client import Client
from paddle_billing.Entities.ClientToken import ClientToken
from paddle_billing.Entities.Collections import ClientTokenCollection
from paddle_billing.Entities.CustomerPortalSession import CustomerPortalSession
from paddle_billing.Entities.CustomerPortalSessions.CustomerPortalSessionSubscriptionUrl import (
    CustomerPortalSessionSubscriptionUrl,
)
from paddle_billing.Entities.PricePreview import PricePreview
from paddle_billing.Entities.Transaction import Transaction
from paddle_billing.Entities.TransactionPreview import TransactionPreview
from paddle_billing.Resources.ClientTokens.Operations import CreateClientToken, ListClientTokens
from paddle_billing.Resources.CustomerPortalSessions.Operations import CreateCustomerPortalSession
from paddle_billing.Resources.PricingPreviews.Operations import PreviewPrice
from paddle_billing.Resources.Transactions.Operations import (
    CreateTransaction,
    PreviewTransaction,
    PreviewTransactionByAddress,
    PreviewTransactionByCustomer,
    PreviewTransactionByIP,
    TransactionIncludes,
)


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    transaction: Transaction
    client_token: ClientToken | None = None
    pricing_preview: PricePreview | None = None

    @property
    def checkout_url(self) -> str | None:
        checkout = getattr(self.transaction, "checkout", None)
        return getattr(checkout, "url", None)

    @property
    def url(self) -> str | None:
        return self.checkout_url


class SessionHelpers:
    def __init__(self, client: Client):
        self.client = client

    def create_client_token(
        self,
        token: str | CreateClientToken,
        *,
        description: str | None = None,
    ) -> ClientToken:
        operation = (
            token
            if isinstance(token, CreateClientToken)
            else CreateClientToken(name=token, description=description)
        )
        return self.client.client_tokens.create(operation)

    def list_client_tokens(
        self,
        operation: ListClientTokens | None = None,
    ) -> ClientTokenCollection:
        return self.client.client_tokens.list(operation)

    def get_client_token(self, client_token_id: str) -> ClientToken:
        return self.client.client_tokens.get(client_token_id)

    def revoke_client_token(self, client_token_id: str) -> ClientToken:
        return self.client.client_tokens.revoke(client_token_id)


class PortalHelpers:
    def __init__(self, client: Client):
        self.client = client

    @staticmethod
    def _normalize_subscription_ids(
        subscription_ids: Sequence[str] | None,
    ) -> list[str] | None:
        if subscription_ids is None:
            return None
        if isinstance(subscription_ids, str):
            return [subscription_ids]
        return list(subscription_ids)

    def create_portal_session(
        self,
        customer_id: str,
        *,
        subscription_ids: Sequence[str] | None = None,
        operation: CreateCustomerPortalSession | None = None,
    ) -> CustomerPortalSession:
        if operation is not None and subscription_ids is not None:
            raise ValueError("Pass either subscription_ids or operation, not both.")

        if operation is None:
            normalized_subscription_ids = self._normalize_subscription_ids(subscription_ids)
            operation = (
                CreateCustomerPortalSession(subscription_ids=normalized_subscription_ids)
                if normalized_subscription_ids is not None
                else CreateCustomerPortalSession()
            )

        return self.client.customer_portal_sessions.create(customer_id, operation)

    def overview_url(
        self,
        customer_id: str,
        *,
        subscription_ids: Sequence[str] | None = None,
        operation: CreateCustomerPortalSession | None = None,
    ) -> str:
        session = self.create_portal_session(
            customer_id,
            subscription_ids=subscription_ids,
            operation=operation,
        )
        return session.urls.general.overview

    def subscription_urls(
        self,
        customer_id: str,
        *,
        subscription_ids: Sequence[str] | None = None,
        operation: CreateCustomerPortalSession | None = None,
    ) -> dict[str, CustomerPortalSessionSubscriptionUrl]:
        session = self.create_portal_session(
            customer_id,
            subscription_ids=subscription_ids,
            operation=operation,
        )
        return {item.id: item for item in session.urls.subscriptions}


class CheckoutHelpers:
    def __init__(self, client: Client):
        self.client = client
        self.sessions = SessionHelpers(client)

    def create_transaction(
        self,
        operation: CreateTransaction,
        *,
        includes: Sequence[TransactionIncludes] | None = None,
    ) -> Transaction:
        return self.client.transactions.create(operation, includes=list(includes or []))

    def preview_transaction(
        self,
        operation: (
            PreviewTransaction
            | PreviewTransactionByAddress
            | PreviewTransactionByCustomer
            | PreviewTransactionByIP
        ),
    ) -> TransactionPreview:
        return self.client.transactions.preview(operation)

    def preview_prices(self, operation: PreviewPrice) -> PricePreview:
        return self.client.pricing_previews.preview_prices(operation)

    def create_checkout_session(
        self,
        transaction_operation: CreateTransaction,
        *,
        includes: Sequence[TransactionIncludes] | None = None,
        client_token: str | CreateClientToken | None = None,
        client_token_description: str | None = None,
        pricing_preview_operation: PreviewPrice | None = None,
    ) -> CheckoutSession:
        pricing_preview = (
            self.preview_prices(pricing_preview_operation)
            if pricing_preview_operation is not None
            else None
        )
        client_token_result = None
        if client_token is not None:
            client_token_result = self.sessions.create_client_token(
                client_token,
                description=client_token_description,
            )

        try:
            transaction = self.create_transaction(transaction_operation, includes=includes)
        except Exception as exc:
            if client_token_result is not None:
                try:
                    self.sessions.revoke_client_token(client_token_result.id)
                except Exception as revoke_exc:
                    exc.add_note(
                        "Failed to revoke Paddle client token "
                        f"{client_token_result.id}: {revoke_exc}"
                    )
            raise

        return CheckoutSession(
            transaction=transaction,
            client_token=client_token_result,
            pricing_preview=pricing_preview,
        )
