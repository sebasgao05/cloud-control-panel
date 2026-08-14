"""
Cloud Control Panel - Shared utilities.
DynamoDB helpers, response helper, decimal conversion, constants, migration.
"""

import json
import logging
import os
import uuid
from decimal import Decimal

import bcrypt
import boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "us-east-1")
CONFIG_TABLE = os.environ.get("CONFIG_TABLE", "cloud-control-config-ccp-main")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# EC2 pricing (On-Demand, us-east-1, Linux, USD/hour)
EC2_PRICING = {
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
}

# DynamoDB resource (reused across invocations)
_ddb = None
_table = None


def get_table():
    global _ddb, _table
    if _table is None:
        _ddb = boto3.resource("dynamodb", region_name=REGION)
        _table = _ddb.Table(CONFIG_TABLE)
    return _table


def db_get(pk, sk):
    """Get a single item from DynamoDB."""
    resp = get_table().get_item(Key={"PK": pk, "SK": sk})
    return resp.get("Item")


def db_put(item):
    """Put an item into DynamoDB."""
    get_table().put_item(Item=item)


def db_delete(pk, sk):
    """Delete an item from DynamoDB."""
    get_table().delete_item(Key={"PK": pk, "SK": sk})


def db_query(pk, sk_prefix=None):
    """Query items by PK and optional SK prefix."""
    table = get_table()
    if sk_prefix:
        resp = table.query(KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix))
    else:
        resp = table.query(KeyConditionExpression=Key("PK").eq(pk))
    return resp.get("Items", [])


def db_query_between(pk, sk_start, sk_end):
    """Query items by PK with SK between two values (inclusive)."""
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").between(sk_start, sk_end)
    )
    return resp.get("Items", [])


def decimal_to_native(obj):
    """Convert Decimal types from DynamoDB to Python native types."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_native(i) for i in obj]
    return obj


def load_config_from_db():
    """Load full config from DynamoDB (reconstructed)."""
    settings_item = db_get("CONFIG", "SETTINGS")
    settings = (
        decimal_to_native(settings_item.get("data", {}))
        if settings_item
        else {"defaultRegion": "us-east-1", "pollIntervalSeconds": 30, "timezone": "America/Bogota"}
    )

    key_items = db_query("CONFIG", "APIKEY#")
    api_keys = {}
    for item in key_items:
        key_id = item["SK"].replace("APIKEY#", "")
        data = decimal_to_native(item.get("data", {}))
        api_keys[key_id] = data

    account_items = db_query("CONFIG", "ACCOUNT#")
    account_map = {}
    for item in account_items:
        acc_id = item["SK"].replace("ACCOUNT#", "")
        account_map[acc_id] = decimal_to_native(item.get("data", {}))
        account_map[acc_id]["id"] = acc_id
        account_map[acc_id].setdefault("instances", [])
        account_map[acc_id].setdefault("groups", [])
        account_map[acc_id].setdefault("features", {})
        account_map[acc_id].setdefault("schedule", {"timezone": "America/Bogota", "rules": []})
        account_map[acc_id].setdefault("notifications", {"channels": []})

    for acc_id in account_map:
        inst_items = db_query(f"ACCOUNT#{acc_id}", "INSTANCE#")
        account_map[acc_id]["instances"] = [decimal_to_native(i.get("data", {})) for i in inst_items]
        grp_items = db_query(f"ACCOUNT#{acc_id}", "GROUP#")
        account_map[acc_id]["groups"] = [decimal_to_native(g.get("data", {})) for g in grp_items]
        res_items = db_query(f"ACCOUNT#{acc_id}", "RESOURCE#")
        account_map[acc_id]["resources"] = [decimal_to_native(r.get("data", {})) for r in res_items]
        sched_items = db_query(f"ACCOUNT#{acc_id}", "SCHEDULE#")
        account_map[acc_id]["schedule"]["rules"] = [decimal_to_native(s.get("data", {})) for s in sched_items]
        ch_items = db_query(f"ACCOUNT#{acc_id}", "CHANNEL#")
        account_map[acc_id]["notifications"]["channels"] = [decimal_to_native(c.get("data", {})) for c in ch_items]

    accounts = list(account_map.values())
    return {"settings": settings, "apiKeys": api_keys, "accounts": accounts}


def is_db_initialized():
    """Check if DynamoDB has config data."""
    item = db_get("CONFIG", "SETTINGS")
    return item is not None


def migrate_json_to_db(json_config):
    """Migrate a JSON config to DynamoDB."""
    db_put({"PK": "CONFIG", "SK": "SETTINGS", "data": json_config.get("settings", {})})

    for key_id, key_data in json_config.get("apiKeys", {}).items():
        db_put({"PK": "CONFIG", "SK": f"APIKEY#{key_id}", "data": key_data})

    for acc in json_config.get("accounts", []):
        acc_id = acc["id"]
        acc_meta = {k: v for k, v in acc.items() if k not in ("instances", "groups", "schedule", "notifications", "id")}
        db_put({"PK": "CONFIG", "SK": f"ACCOUNT#{acc_id}", "data": acc_meta})

        for inst in acc.get("instances", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"INSTANCE#{inst['id']}", "data": inst})

        for grp in acc.get("groups", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"GROUP#{grp['id']}", "data": grp})

        for rule in acc.get("schedule", {}).get("rules", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"SCHEDULE#{rule['id']}", "data": rule})

        for ch in acc.get("notifications", {}).get("channels", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"CHANNEL#{ch['id']}", "data": ch})

    logger.info("[MIGRATE] JSON config migrated to DynamoDB successfully")


def is_keys_migrated():
    """Check if API keys have been migrated to bcrypt hashes."""
    item = db_get("CONFIG", "KEYS_MIGRATED")
    return item is not None


def migrate_plaintext_keys_to_bcrypt():
    """
    Migrate plaintext API keys to bcrypt hashes (one-time operation).

    Before migration: PK=CONFIG, SK=APIKEY#{plaintext_key}, data={name, role, accounts[], ...}
    After migration:  PK=CONFIG, SK=APIKEY#{uuid}, data={hash: bcrypt_hash, name, role, accounts[], ...}

    Sets a CONFIG/KEYS_MIGRATED flag to prevent re-running.
    """
    if is_keys_migrated():
        return

    logger.info("[MIGRATE] Starting plaintext keys to bcrypt migration...")

    key_items = db_query("CONFIG", "APIKEY#")
    migrated_count = 0

    for item in key_items:
        old_sk = item["SK"]
        plaintext_key = old_sk.replace("APIKEY#", "")
        data = item.get("data", {})

        # Skip if already migrated (has a hash field)
        if data.get("hash"):
            continue

        # Generate bcrypt hash of the plaintext key
        key_hash = bcrypt.hashpw(plaintext_key.encode("utf-8"), bcrypt.gensalt())

        # Generate a new UUID as the key identifier
        new_key_id = str(uuid.uuid4())

        # Build new data with hash
        new_data = {**data, "hash": key_hash.decode("utf-8")}

        # Write new item with UUID-based SK
        db_put({"PK": "CONFIG", "SK": f"APIKEY#{new_key_id}", "data": new_data})

        # Delete old plaintext-keyed item
        db_delete("CONFIG", old_sk)

        migrated_count += 1
        logger.info(f"[MIGRATE] Migrated key to id={new_key_id}")

    # Set migration flag
    db_put({"PK": "CONFIG", "SK": "KEYS_MIGRATED", "data": {"migrated": True, "count": migrated_count}})
    logger.info(f"[MIGRATE] Completed bcrypt migration. {migrated_count} keys migrated.")


def sanitize_error(status_code):
    """Return a generic error message for the given HTTP status code.

    Never expose internal error details to clients.
    """
    messages = {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not found",
        405: "Method not allowed",
        409: "Conflict",
        429: "Too many requests",
        500: "Internal server error",
        502: "Bad gateway",
        503: "Service unavailable",
    }
    return messages.get(status_code, "Internal server error")


def response(status_code, body):
    """Standard API response helper.

    CORS is handled at the API Gateway level (template.yaml CorsConfiguration).
    Only Content-Type header is set here.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=str),
    }
