# django-paddle-mor

`django-paddle-mor` is a Django app inspired by `dj-stripe`, but built for Paddle Billing.
It mirrors Paddle resources into Django models, verifies and ingests webhooks, and exposes
sync commands backed by the official `paddle-python-sdk`.

## What it includes

- installable Django app
- typed package settings
- broad Paddle Billing model coverage with raw payload storage
- webhook signature verification and event ingestion
- generic sync command for supported Paddle resources
- checkout, session, pricing-preview, and portal helper APIs
- Django admin registration for synced resources

## Install

```bash
pip install django-paddle-mor
```

## Configure

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django_paddle_mor",
]
```

Configure package settings:

```python
DJANGO_PADDLE_MOR = {
    "API_KEY": "pdl_live_xxx",
    "WEBHOOK_SECRETS": ["pdl_ntfset_xxx"],
    "SANDBOX": False,
}
```

Include the webhook URL:

```python
from django.urls import include, path

urlpatterns = [
    path("billing/", include("django_paddle_mor.urls")),
]
```

## Sync resources

```bash
python manage.py sync_paddle_resources products
python manage.py sync_paddle_resources subscriptions
python manage.py sync_paddle_resources addresses cus_123 --limit 10
python manage.py sync_paddle_resources addresses cus_123 add_456
python manage.py sync_paddle_resources all --limit 10
```

`all` syncs the resources that Paddle exposes through zero-argument list endpoints. Nested
resources such as addresses, businesses, payment methods, notification logs, and simulation
run resources need lookup identifiers so the package can scope the SDK call correctly.

## Checkout, session, and portal helpers

```python
from django_paddle_mor import PaddleAPI
from paddle_billing.Entities.PricingPreviews import PricePreviewItem
from paddle_billing.Resources.PricingPreviews.Operations import PreviewPrice
from paddle_billing.Resources.Transactions.Operations import CreateTransaction
from paddle_billing.Resources.Transactions.Operations.Create import TransactionCreateItem

api = PaddleAPI()

checkout_session = api.checkout.create_checkout_session(
    CreateTransaction(
        items=[TransactionCreateItem(price_id="pri_123", quantity=1)],
    ),
    client_token="Website checkout",
    pricing_preview_operation=PreviewPrice(
        items=[PricePreviewItem(price_id="pri_123", quantity=1)],
    ),
)

checkout_session.url
checkout_session.client_token.token

portal_url = api.portal.overview_url("cus_123")
```

Use the helper namespaces for the non-persisted Paddle Billing surfaces:

- `api.checkout` for transaction-backed checkout creation and pricing previews
- `api.sessions` for client token lifecycle helpers
- `api.portal` for customer portal session and URL helpers
