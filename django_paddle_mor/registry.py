from __future__ import annotations

from collections.abc import Mapping

from .exceptions import UnsupportedResourceError

CLIENT_TOKEN_ALIAS = "_".join(("client", "token"))
CLIENT_TOKEN_RESOURCE_NAME = "_".join(("client", "tokens"))

CANONICAL_RESOURCE_NAMES = (
    "addresses",
    "adjustments",
    "businesses",
    CLIENT_TOKEN_RESOURCE_NAME,
    "customer_portal_sessions",
    "customers",
    "discount_groups",
    "discounts",
    "event_types",
    "events",
    "ip_addresses",
    "metrics",
    "notification_logs",
    "notification_settings",
    "notifications",
    "payment_methods",
    "prices",
    "pricing_previews",
    "products",
    "reports",
    "simulation_run_events",
    "simulation_runs",
    "simulation_types",
    "simulations",
    "subscriptions",
    "transactions",
)

SERVICE_RESOURCE_NAMES = frozenset(
    {
        CLIENT_TOKEN_RESOURCE_NAME,
        "customer_portal_sessions",
        "ip_addresses",
        "metrics",
        "pricing_previews",
    }
)

PERSISTED_RESOURCE_NAMES = frozenset(
    resource_name
    for resource_name in CANONICAL_RESOURCE_NAMES
    if resource_name not in SERVICE_RESOURCE_NAMES
)

RESOURCE_ALIASES: Mapping[str, str] = {
    "address": "addresses",
    "addresses": "addresses",
    "adjustment": "adjustments",
    "adjustments": "adjustments",
    "business": "businesses",
    "businesses": "businesses",
    CLIENT_TOKEN_ALIAS: CLIENT_TOKEN_RESOURCE_NAME,
    CLIENT_TOKEN_RESOURCE_NAME: CLIENT_TOKEN_RESOURCE_NAME,
    "customer": "customers",
    "customer_portal": "customer_portal_sessions",
    "customer_portals": "customer_portal_sessions",
    "customer_portal_session": "customer_portal_sessions",
    "customer_portal_sessions": "customer_portal_sessions",
    "customers": "customers",
    "discount": "discounts",
    "discount_group": "discount_groups",
    "discount_groups": "discount_groups",
    "discounts": "discounts",
    "event": "events",
    "event_type": "event_types",
    "event_types": "event_types",
    "events": "events",
    "ip_address": "ip_addresses",
    "ip_addresses": "ip_addresses",
    "metric": "metrics",
    "metrics": "metrics",
    "notification": "notifications",
    "notification_log": "notification_logs",
    "notification_logs": "notification_logs",
    "notification_setting": "notification_settings",
    "notification_settings": "notification_settings",
    "notifications": "notifications",
    "payment_method": "payment_methods",
    "payment_methods": "payment_methods",
    "price": "prices",
    "prices": "prices",
    "pricing_preview": "pricing_previews",
    "pricing_previews": "pricing_previews",
    "product": "products",
    "products": "products",
    "report": "reports",
    "reports": "reports",
    "simulation": "simulations",
    "simulation_run": "simulation_runs",
    "simulation_run_event": "simulation_run_events",
    "simulation_run_events": "simulation_run_events",
    "simulation_runs": "simulation_runs",
    "simulation_type": "simulation_types",
    "simulation_types": "simulation_types",
    "simulations": "simulations",
    "subscription": "subscriptions",
    "subscriptions": "subscriptions",
    "transaction": "transactions",
    "transactions": "transactions",
}


def normalize_resource_name(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(".", "_").replace(" ", "_")


def resolve_resource_name(value: str) -> str:
    normalized = normalize_resource_name(value)
    try:
        return RESOURCE_ALIASES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(CANONICAL_RESOURCE_NAMES))
        raise UnsupportedResourceError(
            f"Unsupported Paddle resource '{value}'. Supported resources: {supported}."
        ) from exc


def resource_name_from_event_type(event_type: str) -> str | None:
    if not event_type:
        return None

    normalized_prefix = normalize_resource_name(event_type.split(".", 1)[0])
    return RESOURCE_ALIASES.get(normalized_prefix)
