"""
Cloud Control Panel - Authentication and authorization helpers.
"""

import bcrypt

from utils import logger


def authenticate(event, config):
    """
    Authenticate request via x-api-key header.

    After migration to bcrypt hashing, keys are stored as:
        PK=CONFIG, SK=APIKEY#{key_id}, data={hash: bcrypt_hash, name, role, accounts[], ...}

    We iterate all stored keys and use bcrypt.checkpw to find a match.
    This is acceptable for a single-user/small-team system.

    Note: The mock server (mock/server.py) continues to use plaintext key lookup
    for local development since it does not use DynamoDB or bcrypt.
    """
    headers = event.get("headers", {})
    provided_key = headers.get("x-api-key", "")
    if not provided_key:
        return None

    api_keys = config.get("apiKeys", {})

    for key_id, key_data in api_keys.items():
        stored_hash = key_data.get("hash")
        if stored_hash:
            # Migrated key: validate via bcrypt
            try:
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode("utf-8")
                if bcrypt.checkpw(provided_key.encode("utf-8"), stored_hash):
                    return key_data
            except (ValueError, TypeError) as e:
                logger.error(f"[AUTH] bcrypt check failed for key_id={key_id}: {e}")
                continue
        else:
            # Legacy plaintext key (pre-migration): key_id IS the plaintext key
            if key_id == provided_key:
                return key_data

    return None


def get_allowed_accounts(user_info, config):
    """Get accounts the user has access to."""
    all_accounts = config.get("accounts", [])
    allowed = user_info.get("accounts", [])
    if "*" in allowed:
        return all_accounts
    return [acc for acc in all_accounts if acc["id"] in allowed]


def find_instance(account, instance_id):
    """Find an instance by ID within an account."""
    return next((i for i in account.get("instances", []) if i["id"] == instance_id), None)


def find_group(account, group_id):
    """Find a group by ID within an account."""
    return next((g for g in account.get("groups", []) if g["id"] == group_id), None)


def get_scheduler_permissions(user_info):
    """Get scheduler permissions for a user."""
    if user_info.get("role") == "superadmin":
        return {"view": True, "edit": True}
    if user_info.get("role") == "admin":
        return {"view": False, "edit": False}
    sched = user_info.get("scheduler", {})
    can_edit = sched.get("edit", False)
    return {"view": can_edit or sched.get("view", False), "edit": can_edit}


def is_admin(user_info):
    """Check if user is admin or superadmin."""
    return user_info.get("role") in ("admin", "superadmin")


def is_superadmin(user_info):
    """Check if user is superadmin."""
    return user_info.get("role") == "superadmin"
