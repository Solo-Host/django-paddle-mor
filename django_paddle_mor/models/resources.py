from __future__ import annotations

from django.db import models

from django_paddle_mor.exceptions import MissingPaddleIdentifierError

from .base import AbstractPaddleResource, _coerce_datetime


def _payload_dict(payload, key: str) -> dict:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _payload_list(payload, key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _payload_str(payload, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _extract_related_id(payload, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str) and identifier:
                return identifier
    return ""


def _related_instance(model_class, paddle_id: str):
    if not paddle_id:
        return None
    return model_class.objects.filter(paddle_id=paddle_id).first()


class Address(AbstractPaddleResource):
    RESOURCE_NAME = "addresses"
    EVENT_PREFIXES = ("address",)


class Adjustment(AbstractPaddleResource):
    RESOURCE_NAME = "adjustments"
    EVENT_PREFIXES = ("adjustment",)


class Business(AbstractPaddleResource):
    RESOURCE_NAME = "businesses"
    EVENT_PREFIXES = ("business",)


class Customer(AbstractPaddleResource):
    RESOURCE_NAME = "customers"
    EVENT_PREFIXES = ("customer",)

    email = models.EmailField(blank=True)
    marketing_consent = models.BooleanField(default=False)
    locale = models.CharField(max_length=32, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    subscriber_model_label = models.CharField(max_length=255, blank=True)
    subscriber_object_id = models.CharField(max_length=64, blank=True)

    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        defaults.update(
            email=_payload_str(payload, "email"),
            marketing_consent=bool(payload.get("marketing_consent", False)),
            locale=_payload_str(payload, "locale"),
            custom_data=_payload_dict(payload, "custom_data"),
        )
        return defaults

    @property
    def subscriber(self):
        if not self.subscriber_model_label or not self.subscriber_object_id:
            return None

        from django.apps import apps as django_apps

        try:
            subscriber_model = django_apps.get_model(self.subscriber_model_label)
        except (LookupError, ValueError):
            return None

        return subscriber_model._default_manager.filter(pk=self.subscriber_object_id).first()

    def link_subscriber(self, subscriber) -> None:
        self.subscriber_model_label = subscriber._meta.label
        self.subscriber_object_id = str(subscriber.pk)
        self.save(update_fields=["subscriber_model_label", "subscriber_object_id", "updated_at"])

    @classmethod
    def sync_from_payload(cls, payload, *, source: str = "api"):
        instance = super().sync_from_payload(payload, source=source)

        from django_paddle_mor.subscriber import auto_link_customer_to_subscriber

        Subscription.objects.filter(
            customer__isnull=True,
            customer_external_id=instance.paddle_id,
        ).update(customer=instance)
        Transaction.objects.filter(
            customer__isnull=True,
            customer_external_id=instance.paddle_id,
        ).update(customer=instance)
        auto_link_customer_to_subscriber(instance)
        return instance


class Discount(AbstractPaddleResource):
    RESOURCE_NAME = "discounts"
    EVENT_PREFIXES = ("discount",)


class DiscountGroup(AbstractPaddleResource):
    RESOURCE_NAME = "discount_groups"
    EVENT_PREFIXES = ("discount_group",)


class Event(AbstractPaddleResource):
    RESOURCE_NAME = "events"
    EVENT_PREFIXES = ("event",)


class EventType(AbstractPaddleResource):
    RESOURCE_NAME = "event_types"
    EVENT_PREFIXES = ("event_type",)

    @classmethod
    def extract_paddle_id(cls, payload):
        name = payload.get("name")
        if not name:
            raise MissingPaddleIdentifierError(
                f"{cls.__name__} payload is missing the 'name' field required for synchronization."
            )
        return str(name)


class Notification(AbstractPaddleResource):
    RESOURCE_NAME = "notifications"
    EVENT_PREFIXES = ("notification",)


class NotificationLog(AbstractPaddleResource):
    RESOURCE_NAME = "notification_logs"
    EVENT_PREFIXES = ("notification_log",)


class NotificationSetting(AbstractPaddleResource):
    RESOURCE_NAME = "notification_settings"
    EVENT_PREFIXES = ("notification_setting",)


class PaymentMethod(AbstractPaddleResource):
    RESOURCE_NAME = "payment_methods"
    EVENT_PREFIXES = ("payment_method",)


class Price(AbstractPaddleResource):
    RESOURCE_NAME = "prices"
    EVENT_PREFIXES = ("price",)

    product = models.ForeignKey(
        "Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prices",
    )
    product_external_id = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    catalog_type = models.CharField(max_length=32, blank=True)
    tax_mode = models.CharField(max_length=32, blank=True)
    billing_cycle = models.JSONField(default=dict, blank=True)
    trial_period = models.JSONField(default=dict, blank=True)
    unit_price = models.JSONField(default=dict, blank=True)
    unit_price_amount = models.CharField(max_length=64, blank=True)
    unit_price_currency_code = models.CharField(max_length=8, blank=True)
    quantity = models.JSONField(default=dict, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        product_external_id = _extract_related_id(payload, "product_id", "product")
        unit_price = _payload_dict(payload, "unit_price")
        defaults.update(
            product=_related_instance(Product, product_external_id),
            product_external_id=product_external_id,
            description=_payload_str(payload, "description"),
            catalog_type=_payload_str(payload, "type"),
            tax_mode=_payload_str(payload, "tax_mode"),
            billing_cycle=_payload_dict(payload, "billing_cycle"),
            trial_period=_payload_dict(payload, "trial_period"),
            unit_price=unit_price,
            unit_price_amount=_payload_str(unit_price, "amount"),
            unit_price_currency_code=_payload_str(unit_price, "currency_code"),
            quantity=_payload_dict(payload, "quantity"),
            custom_data=_payload_dict(payload, "custom_data"),
        )
        return defaults


class Product(AbstractPaddleResource):
    RESOURCE_NAME = "products"
    EVENT_PREFIXES = ("product",)

    description = models.TextField(blank=True)
    tax_category = models.CharField(max_length=64, blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    catalog_type = models.CharField(max_length=32, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        defaults.update(
            description=_payload_str(payload, "description"),
            tax_category=_payload_str(payload, "tax_category"),
            image_url=_payload_str(payload, "image_url"),
            catalog_type=_payload_str(payload, "type"),
            custom_data=_payload_dict(payload, "custom_data"),
        )
        return defaults

    @classmethod
    def sync_from_payload(cls, payload, *, source: str = "api"):
        instance = super().sync_from_payload(payload, source=source)
        Price.objects.filter(product__isnull=True, product_external_id=instance.paddle_id).update(
            product=instance
        )
        return instance


class Report(AbstractPaddleResource):
    RESOURCE_NAME = "reports"
    EVENT_PREFIXES = ("report",)


class Simulation(AbstractPaddleResource):
    RESOURCE_NAME = "simulations"
    EVENT_PREFIXES = ("simulation",)


class SimulationRun(AbstractPaddleResource):
    RESOURCE_NAME = "simulation_runs"
    EVENT_PREFIXES = ("simulation_run",)


class SimulationRunEvent(AbstractPaddleResource):
    RESOURCE_NAME = "simulation_run_events"
    EVENT_PREFIXES = ("simulation_run_event",)


class SimulationType(AbstractPaddleResource):
    RESOURCE_NAME = "simulation_types"
    EVENT_PREFIXES = ("simulation_type",)

    @classmethod
    def extract_paddle_id(cls, payload):
        name = payload.get("name")
        if not name:
            raise MissingPaddleIdentifierError(
                f"{cls.__name__} payload is missing the 'name' field required for synchronization."
            )
        return str(name)


class Subscription(AbstractPaddleResource):
    RESOURCE_NAME = "subscriptions"
    EVENT_PREFIXES = ("subscription",)

    customer = models.ForeignKey(
        "Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subscriptions",
    )
    customer_external_id = models.CharField(max_length=128, blank=True)
    address_external_id = models.CharField(max_length=128, blank=True)
    business_external_id = models.CharField(max_length=128, blank=True)
    currency_code = models.CharField(max_length=8, blank=True)
    collection_mode = models.CharField(max_length=32, blank=True)
    billing_cycle = models.JSONField(default=dict, blank=True)
    current_billing_period = models.JSONField(default=dict, blank=True)
    scheduled_change = models.JSONField(default=dict, blank=True)
    management_urls = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    first_billed_at = models.DateTimeField(null=True, blank=True)
    next_billed_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        customer_external_id = _extract_related_id(payload, "customer_id", "customer")
        defaults.update(
            customer=_related_instance(Customer, customer_external_id),
            customer_external_id=customer_external_id,
            address_external_id=_extract_related_id(payload, "address_id", "address"),
            business_external_id=_extract_related_id(payload, "business_id", "business"),
            currency_code=_payload_str(payload, "currency_code"),
            collection_mode=_payload_str(payload, "collection_mode"),
            billing_cycle=_payload_dict(payload, "billing_cycle"),
            current_billing_period=_payload_dict(payload, "current_billing_period"),
            scheduled_change=_payload_dict(payload, "scheduled_change"),
            management_urls=_payload_dict(payload, "management_urls"),
            items=_payload_list(payload, "items"),
            custom_data=_payload_dict(payload, "custom_data"),
            started_at=_coerce_datetime(payload.get("started_at")),
            first_billed_at=_coerce_datetime(payload.get("first_billed_at")),
            next_billed_at=_coerce_datetime(payload.get("next_billed_at")),
            paused_at=_coerce_datetime(payload.get("paused_at")),
            canceled_at=_coerce_datetime(payload.get("canceled_at")),
        )
        return defaults

    @classmethod
    def sync_from_payload(cls, payload, *, source: str = "api"):
        instance = super().sync_from_payload(payload, source=source)
        Transaction.objects.filter(
            subscription__isnull=True,
            subscription_external_id=instance.paddle_id,
        ).update(subscription=instance)
        return instance


class Transaction(AbstractPaddleResource):
    RESOURCE_NAME = "transactions"
    EVENT_PREFIXES = ("transaction",)

    customer = models.ForeignKey(
        "Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    subscription = models.ForeignKey(
        "Subscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    customer_external_id = models.CharField(max_length=128, blank=True)
    subscription_external_id = models.CharField(max_length=128, blank=True)
    address_external_id = models.CharField(max_length=128, blank=True)
    business_external_id = models.CharField(max_length=128, blank=True)
    discount_external_id = models.CharField(max_length=128, blank=True)
    currency_code = models.CharField(max_length=8, blank=True)
    origin = models.CharField(max_length=32, blank=True)
    collection_mode = models.CharField(max_length=32, blank=True)
    invoice_id = models.CharField(max_length=128, blank=True)
    invoice_number = models.CharField(max_length=128, blank=True)
    billing_details = models.JSONField(default=dict, blank=True)
    billing_period = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list, blank=True)
    payments = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    billed_at = models.DateTimeField(null=True, blank=True)
    revised_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        customer_external_id = _extract_related_id(payload, "customer_id", "customer")
        subscription_external_id = _extract_related_id(
            payload,
            "subscription_id",
            "subscription",
        )
        checkout = _payload_dict(payload, "checkout")
        defaults.update(
            customer=_related_instance(Customer, customer_external_id),
            subscription=_related_instance(Subscription, subscription_external_id),
            customer_external_id=customer_external_id,
            subscription_external_id=subscription_external_id,
            address_external_id=_extract_related_id(payload, "address_id", "address"),
            business_external_id=_extract_related_id(payload, "business_id", "business"),
            discount_external_id=_extract_related_id(payload, "discount_id", "discount"),
            currency_code=_payload_str(payload, "currency_code"),
            origin=_payload_str(payload, "origin"),
            collection_mode=_payload_str(payload, "collection_mode"),
            invoice_id=_payload_str(payload, "invoice_id"),
            invoice_number=_payload_str(payload, "invoice_number"),
            billing_details=_payload_dict(payload, "billing_details"),
            billing_period=_payload_dict(payload, "billing_period"),
            details=_payload_dict(payload, "details"),
            items=_payload_list(payload, "items"),
            payments=_payload_list(payload, "payments"),
            custom_data=_payload_dict(payload, "custom_data"),
            checkout_url=_payload_str(checkout, "url"),
            billed_at=_coerce_datetime(payload.get("billed_at")),
            revised_at=_coerce_datetime(payload.get("revised_at")),
        )
        return defaults


RESOURCE_MODELS = (
    Address,
    Adjustment,
    Business,
    Customer,
    Discount,
    DiscountGroup,
    Event,
    EventType,
    Notification,
    NotificationLog,
    NotificationSetting,
    PaymentMethod,
    Price,
    Product,
    Report,
    Simulation,
    SimulationRun,
    SimulationRunEvent,
    SimulationType,
    Subscription,
    Transaction,
)

RESOURCE_MODEL_REGISTRY = {model.RESOURCE_NAME: model for model in RESOURCE_MODELS}

EVENT_PREFIX_REGISTRY = {}
for model in RESOURCE_MODELS:
    for event_prefix in model.EVENT_PREFIXES:
        EVENT_PREFIX_REGISTRY[event_prefix] = model
