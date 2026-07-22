# Copilot Instructions for django-paddle-mor

## Quick Start

This is a Django package that mirrors Paddle Billing resources into Django models, verifies webhooks, and syncs data. It's built for the official `paddle-python-sdk`, not Paddle Classic.

**Setup:** Use `uv` for dependency management. Run `uv sync --extra dev` to install the local tooling set, then use `uv run ...` for commands. This repository currently targets Python 3.13 only.

`uv.lock` is committed. Update it when dependency metadata changes, and keep CI compatible with `uv sync --frozen --extra dev`.

## Build, Test, and Lint Commands

### Setup and Packaging
```bash
# Install the development toolchain
uv sync --extra dev

# Build wheel and sdist artifacts
uv run python -m build
```

### Tox Entry Points
```bash
# Run the default locally available tox environments
uv run tox

# Run one environment explicitly
uv run tox -e py313
uv run tox -e lint
uv run tox -e mypy
uv run tox -e security

# Run a single test file or test function through tox
uv run tox -e py313 -- tests/test_webhooks.py
uv run tox -e py313 -- tests/test_webhooks.py::test_webhook_ingests_payload_and_syncs_resource
```

### Direct Commands
```bash
# Run the full pytest suite
uv run pytest

# Run Ruff formatting and linting
uv run ruff format django_paddle_mor tests
uv run ruff check django_paddle_mor tests

# Run mypy with the repository config
uv run mypy django_paddle_mor tests

# Run security tooling directly
uv run bandit -q -r django_paddle_mor -x django_paddle_mor/migrations
uv run pip-audit
```

`tox` is the canonical entry point for local and CI checks. The configured environments are `py313`,
`lint`, `mypy`, and `security`, with optional `ruff`, `bandit`, and `pip-audit` aliases for focused
runs.

## High-Level Architecture

### Core Components

**Models & Resources** (`django_paddle_mor/models/`)
- `resources.py`: Paddle resource models (Product, Price, Customer, Subscription, Transaction, etc.)
- `events.py`: WebhookEvent and WebhookEndpoint for tracking webhook deliveries
- `base.py`: AbstractPaddleResource base class with payload parsing and Django integration
- All resource models store raw Paddle payloads in a `data` JSONField for safety and extensibility

**Client & API** (`django_paddle_mor/client.py`)
- `PaddleAPI`: Main client wrapper that provides:
  - `resource_client()`: Access to paddle-python-sdk resource clients
  - `checkout`, `sessions`, `portal`: Helper namespaces for non-persisted surfaces
  - `verify_webhook()`: Webhook signature verification
- `build_paddle_sdk_client()`: Factory function that reads settings and creates the SDK client

**Webhook Handling** (`django_paddle_mor/views.py`)
- `paddle_webhook()`: Single view handles both global (`/billing/webhooks/paddle/`) and endpoint-specific (`/billing/webhooks/paddle/<uuid>/`) webhook URLs
- Flow: signature verification → payload parsing → event ingestion via `ingest_webhook_payload()`
- Signals at each stage: `webhook_pre_validate`, `webhook_post_validate`, `webhook_pre_process`, `webhook_post_process`, `webhook_processing_error`

**Sync & Ingestion** (`django_paddle_mor/sync.py`, `django_paddle_mor/event_handlers.py`)
- `sync.py`: `ResourceSyncRule` defines list/get endpoint arity for each resource type (e.g., addresses need a customer_id)
- `event_handlers.py`: `ingest_webhook_payload()` parses events, dispatches to handlers, creates/updates models
- Resource models auto-sync into Django via the Paddle SDK during webhook ingestion

**Configuration** (`django_paddle_mor/settings.py`)
- Single dataclass `DjangoPaddleMorSettings` with typed, validated fields
- Coercion functions handle string→proper type conversion (bools, ints, floats, tuples)
- Settings are cached with `@lru_cache`, cleared in tests via `clear_django_paddle_mor_settings_cache()`

**Management Commands** (`django_paddle_mor/management/commands/`)
- `sync_paddle_resources`: Bulk sync resources from Paddle into Django models
- `link_paddle_customers`: Attach local Django users/accounts to synced Paddle customers
- `reprocess_paddle_webhooks`: Retry failed webhook events
- `clear_paddle_webhook_events`: Clean up old webhook records

**Automation** (`.github/workflows/`)
- `ci.yml`: Uses a `detect-changes` gate, one shared `static-analysis` job, and named `lint`,
  `type-check`, `security`, and `test` jobs so branch rulesets can require stable check names
- `release.yml`: Opens a `release-bump/vX.Y.Z` PR from `workflow_dispatch`, then tags and creates a
  GitHub Release after that PR is merged

### Feature Modules

**Permission Validation** (`django_paddle_mor/permission_validation.py`)
- Compares Paddle API key permissions (from webhook metadata) to a manifest
- Sends email alerts if permissions don't match

**API Key Notifications** (`django_paddle_mor/notifications.py`)
- Opt-in email alerts for api_key.* and api_key_exposure.* events
- Can notify on creation, expiry, revocation, exposure, and permission mismatches

**Subscriber Integration** (`django_paddle_mor/subscriber.py`)
- Links Paddle customers to Django users by email
- Optional auto-linking during customer sync if `AUTO_LINK_SUBSCRIBER=True`

## Key Conventions

### Model Definition Pattern
All resource models follow this pattern:
- Inherit from `AbstractPaddleResource`
- Define `RESOURCE_NAME` (plural; must match Paddle SDK naming)
- Define `EVENT_PREFIXES` (tuple of event type prefixes for webhook routing)
- Store raw payload in `data` JSONField
- Add specialized fields (e.g., `Customer.email`, `Subscription.status`)
- Implement `defaults_from_payload()` classmethod to extract fields from Paddle payloads
- Use helper functions: `_payload_str()`, `_payload_dict()`, `_payload_list()`, `_extract_related_id()` for safe payload access

Example (from `Customer`):
```python
class Customer(AbstractPaddleResource):
    RESOURCE_NAME = "customers"
    EVENT_PREFIXES = ("customer",)
    
    email = models.EmailField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    
    @classmethod
    def defaults_from_payload(cls, payload, *, source: str):
        defaults = super().defaults_from_payload(payload, source=source)
        defaults.update(
            email=_payload_str(payload, "email"),
            custom_data=_payload_dict(payload, "custom_data"),
        )
        return defaults
```

### Settings Coercion
Settings use strict type validation and transformation via dedicated `_coerce_*()` functions. All coercers:
- Normalize input (strip, lowercase, replace hyphens/dots)
- Raise `ImproperlyConfigured` with clear error messages if invalid
- Support aliases (e.g., `api_key_created` → `created` in notification settings)

### Sync Rules
Each resource has a `ResourceSyncRule` in `RESOURCE_SYNC_RULES` dict defining:
- `list_arity`: Number of path params for list endpoint (0 = no params, 1+ = requires IDs)
- `get_arity`: Number of path params for get endpoint (None = not available)

Resources with `list_arity == 0` can be synced with `sync_paddle_resources all`.

### Type Annotations
Use PEP 604 union syntax (`str | None` not `Optional[str]`) and `from __future__ import annotations` for forward references. All public functions and class methods have type hints.

### Code Style
- Line length: 100 characters (enforced by Ruff)
- Ignore list: B, E, F, I, UP from Ruff
- Migration files exempt from E501 (line-length) checks
- No Black; Ruff format is used instead
- Imports organized with Ruff: future imports first, then stdlib, then third-party, then local

### Versioning and Release Flow
- `pyproject.toml` is the single source of truth for the package version.
- Normal feature work should not bump the version manually.
- Releases go through the `release.yml` workflow, which creates a `release-bump/vX.Y.Z` branch and
  PR, bumps only `pyproject.toml`, and creates the tag and GitHub Release after merge.

### Test Structure
- Pytest + pytest-django
- Test settings in `tests/settings.py`
- Fixtures in `tests/conftest.py`
- Settings cache cleared before/after each test (autouse fixture)
- Models and webhook fixtures in `tests/paddle_test_support.py`

### Type Checking
- `mypy` intentionally excludes Django migration files.
- Imports from `django` and `paddle_billing` are treated as untyped dependencies; mypy still checks
  the package's internal typing and repository code.

### Security Checks
- `tox -e security` runs both Bandit and pip-audit.
- Bandit scans `django_paddle_mor/` and excludes migrations to avoid migration-generated noise.
- The CI `security` ruleset job reflects the result of the shared static-analysis run, so failures
  for lint, typing, or security must be debugged from `static-analysis` first.

## Important Notes

### Raw Payload Storage
All models store the complete Paddle webhook payload in a `data` JSONField. This allows:
- Future-proofing: New Paddle fields don't require migrations
- Debugging: Full webhook payload always available
- Flexibility: Specialized fields can be added incrementally

### Webhook Signature Verification
The package supports endpoint-specific webhook secrets via `WebhookEndpoint` records. Each endpoint has its own secret(s) and livemode flag. If no endpoint_uuid is provided to the webhook view, global `WEBHOOK_SECRETS` from settings are used.

### No ORM Filtering on Paddle Fields
Avoid using the raw `data` JSONField in Django ORM queries. Instead, extract values to dedicated model fields if you need to filter or search.

### Settings Caching
Settings are cached at module load via `@lru_cache`. This is intentional for performance. In tests, the cache is cleared between tests via the `clear_settings_cache` autouse fixture.

### Subscriber Model is Optional
`SUBSCRIBER_MODEL` is optional. If not configured, subscriber-linking features are unavailable but the package continues to work normally.
