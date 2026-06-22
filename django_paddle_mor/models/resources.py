from __future__ import annotations

from django_paddle_mor.exceptions import MissingPaddleIdentifierError

from .base import AbstractPaddleResource


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


class Product(AbstractPaddleResource):
    RESOURCE_NAME = "products"
    EVENT_PREFIXES = ("product",)


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


class Transaction(AbstractPaddleResource):
    RESOURCE_NAME = "transactions"
    EVENT_PREFIXES = ("transaction",)


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
