from __future__ import annotations

API_KEY_ENTITY_ID = "01gtgztp8f4kek3yd4g1wrksa3"
API_KEY_SECRET_PART_ONE = "q6TGTJyvoIz7LDtXT65bX7"
API_KEY_SECRET_PART_TWO = "AQO"
MODERN_API_KEY_RECORD_ID = f"apikey_{API_KEY_ENTITY_ID}"
MODERN_LIVE_API_KEY = "_".join(
    ["pdl", "live", "apikey", API_KEY_ENTITY_ID, API_KEY_SECRET_PART_ONE, API_KEY_SECRET_PART_TWO]
)
MODERN_SANDBOX_API_KEY = "_".join(
    ["pdl", "sdbx", "apikey", API_KEY_ENTITY_ID, API_KEY_SECRET_PART_ONE, API_KEY_SECRET_PART_TWO]
)
OBFUSCATED_SANDBOX_API_KEY = "_".join(
    ["pdl", "sdbx", "apikey", API_KEY_ENTITY_ID, "****************"]
)
DEFAULT_PERMISSION_MANIFEST = (
    "customer.read",
    "subscription.read",
    "subscription.write",
)


def permission_manifest():
    return DEFAULT_PERMISSION_MANIFEST
