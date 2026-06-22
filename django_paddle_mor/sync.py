from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from .client import PaddleAPI
from .exceptions import NonPersistedResourceError
from .models import RESOURCE_MODEL_REGISTRY
from .registry import PERSISTED_RESOURCE_NAMES, resolve_resource_name, resource_name_from_event_type
from .settings import get_django_paddle_mor_settings


@dataclass(frozen=True, slots=True)
class ResourceSyncRule:
    list_arity: int | None
    get_arity: int | None


RESOURCE_SYNC_RULES = {
    "addresses": ResourceSyncRule(list_arity=1, get_arity=2),
    "adjustments": ResourceSyncRule(list_arity=0, get_arity=None),
    "businesses": ResourceSyncRule(list_arity=1, get_arity=2),
    "customers": ResourceSyncRule(list_arity=0, get_arity=1),
    "discount_groups": ResourceSyncRule(list_arity=0, get_arity=1),
    "discounts": ResourceSyncRule(list_arity=0, get_arity=1),
    "event_types": ResourceSyncRule(list_arity=0, get_arity=None),
    "events": ResourceSyncRule(list_arity=0, get_arity=None),
    "notification_logs": ResourceSyncRule(list_arity=1, get_arity=None),
    "notification_settings": ResourceSyncRule(list_arity=0, get_arity=1),
    "notifications": ResourceSyncRule(list_arity=0, get_arity=1),
    "payment_methods": ResourceSyncRule(list_arity=1, get_arity=2),
    "prices": ResourceSyncRule(list_arity=0, get_arity=1),
    "products": ResourceSyncRule(list_arity=0, get_arity=1),
    "reports": ResourceSyncRule(list_arity=0, get_arity=1),
    "simulation_run_events": ResourceSyncRule(list_arity=2, get_arity=3),
    "simulation_runs": ResourceSyncRule(list_arity=1, get_arity=2),
    "simulation_types": ResourceSyncRule(list_arity=0, get_arity=None),
    "simulations": ResourceSyncRule(list_arity=0, get_arity=1),
    "subscriptions": ResourceSyncRule(list_arity=0, get_arity=1),
    "transactions": ResourceSyncRule(list_arity=0, get_arity=1),
}

ZERO_ARGUMENT_LIST_RESOURCE_NAMES = frozenset(
    resource_name
    for resource_name, rule in RESOURCE_SYNC_RULES.items()
    if rule.list_arity == 0
)


def _serialize_sdk_value(value: Any):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize_sdk_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_sdk_value(item) for item in value]
    if is_dataclass(value):
        return _serialize_sdk_value(asdict(value))
    if hasattr(value, "__dict__"):
        serializable = {
            key: item for key, item in vars(value).items() if not key.startswith("_")
        }
        return _serialize_sdk_value(serializable)
    return str(value)


def _ensure_payload_dict(payload: Any) -> dict[str, Any]:
    serialized = _serialize_sdk_value(payload)
    if isinstance(serialized, dict):
        return serialized
    raise TypeError("Paddle payloads must serialize to dictionaries before synchronization.")


def _require_persisted_resource(canonical_name: str) -> None:
    if canonical_name not in PERSISTED_RESOURCE_NAMES:
        raise NonPersistedResourceError(
            f"{canonical_name} is not a persisted Django model resource."
        )


def sync_payload(resource_name: str, payload: Any, *, source: str = "api"):
    canonical_name = resolve_resource_name(resource_name)
    _require_persisted_resource(canonical_name)
    model_class = RESOURCE_MODEL_REGISTRY[canonical_name]
    payload_dict = _ensure_payload_dict(payload)
    return model_class.sync_from_payload(payload_dict, source=source)


def sync_resource(
    resource_name: str,
    *,
    lookup: Sequence[str] | None = None,
    limit: int | None = None,
):
    canonical_name = resolve_resource_name(resource_name)
    _require_persisted_resource(canonical_name)

    paddle_api = PaddleAPI()
    resource_client = paddle_api.resource_client(canonical_name)
    sync_rule = RESOURCE_SYNC_RULES[canonical_name]

    package_settings = get_django_paddle_mor_settings()
    limit = limit or package_settings.default_sync_limit

    if lookup:
        if sync_rule.get_arity is not None and len(lookup) == sync_rule.get_arity:
            entity = resource_client.get(*lookup)
            return [sync_payload(canonical_name, entity, source="api")]

        if sync_rule.list_arity is not None and len(lookup) == sync_rule.list_arity:
            synced_instances = []
            for index, entity in enumerate(resource_client.list(*lookup)):
                synced_instances.append(sync_payload(canonical_name, entity, source="api"))
                if index + 1 >= limit:
                    break
            return synced_instances

        expected_arities = []
        if sync_rule.list_arity is not None:
            expected_arities.append(f"list arity {sync_rule.list_arity}")
        if sync_rule.get_arity is not None:
            expected_arities.append(f"get arity {sync_rule.get_arity}")
        raise ValueError(
            f"{canonical_name} expected lookup identifiers matching "
            f"{' or '.join(expected_arities)}; received {len(lookup)}."
        )

    if sync_rule.list_arity != 0:
        raise ValueError(
            f"{canonical_name} requires {sync_rule.list_arity} lookup identifier(s) "
            "to perform a list-based sync."
        )

    synced_instances = []
    for index, entity in enumerate(resource_client.list()):
        synced_instances.append(sync_payload(canonical_name, entity, source="api"))
        if index + 1 >= limit:
            break

    return synced_instances


def sync_all_resources(*, limit: int | None = None) -> dict[str, int]:
    results = {}
    for resource_name in sorted(ZERO_ARGUMENT_LIST_RESOURCE_NAMES):
        results[resource_name] = len(sync_resource(resource_name, limit=limit))
    return results


def resource_name_for_event_type(event_type: str) -> str | None:
    resolved = resource_name_from_event_type(event_type)
    if resolved in PERSISTED_RESOURCE_NAMES:
        return resolved
    return None
