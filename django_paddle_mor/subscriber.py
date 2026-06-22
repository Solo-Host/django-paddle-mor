from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured

from .settings import get_django_paddle_mor_settings


def get_subscriber_model():
    settings = get_django_paddle_mor_settings()
    if not settings.subscriber_model:
        return None

    try:
        model = django_apps.get_model(settings.subscriber_model)
    except ValueError as exc:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['SUBSCRIBER_MODEL'] must be of the form 'app_label.ModelName'."
        ) from exc
    except LookupError as exc:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['SUBSCRIBER_MODEL'] refers to a model that is not installed."
        ) from exc

    return model


def validate_subscriber_model_configuration():
    subscriber_model = get_subscriber_model()
    if subscriber_model is None:
        return None

    email_field = get_django_paddle_mor_settings().subscriber_email_field
    try:
        subscriber_model._meta.get_field(email_field)
    except FieldDoesNotExist as exc:
        raise ImproperlyConfigured(
            "DJANGO_PADDLE_MOR['SUBSCRIBER_EMAIL_FIELD'] must reference a field present on "
            f"{subscriber_model._meta.label}."
        ) from exc

    return subscriber_model


def find_subscriber_for_customer(customer):
    subscriber_model = validate_subscriber_model_configuration()
    if subscriber_model is None or not customer.email:
        return None

    email_field = get_django_paddle_mor_settings().subscriber_email_field
    lookup = {email_field: customer.email}

    try:
        return subscriber_model._default_manager.get(**lookup)
    except subscriber_model.DoesNotExist:
        return None
    except subscriber_model.MultipleObjectsReturned:
        return None


def link_customer_to_subscriber(customer):
    if customer.subscriber_model_label and customer.subscriber_object_id:
        existing_subscriber = customer.subscriber
        email_field = get_django_paddle_mor_settings().subscriber_email_field
        if (
            existing_subscriber is not None
            and getattr(existing_subscriber, email_field, None) == customer.email
        ):
            return existing_subscriber

        customer.subscriber_model_label = ""
        customer.subscriber_object_id = ""
        customer.save(
            update_fields=["subscriber_model_label", "subscriber_object_id", "updated_at"]
        )

    subscriber = find_subscriber_for_customer(customer)
    if subscriber is None:
        return None

    customer.link_subscriber(subscriber)
    return subscriber


def auto_link_customer_to_subscriber(customer):
    settings = get_django_paddle_mor_settings()
    if not settings.auto_link_subscriber:
        return None

    return link_customer_to_subscriber(customer)
