"""
Cloud Control Panel - Authentication and authorization helpers.
"""

import hashlib
import time

import bcrypt

from utils import logger

# In-memory auth cache (persists across warm Lambda invocations).
# Maps SHA-256(provided_key) -> (user_info_dict, expiry_timestamp)
# TTL: 5 minutes. This avoids repeated bcrypt comparisons for the same key.
_auth_cache = {}
_AUTH_CACHE_TTL = 300  # seconds


def clear_auth_cache():
    """Clear the auth cache. Used in tests."""
    _auth_cache.clear()


def authenticate(event, config):
    """
    Authenticate request via x-api-key header with in-memory caching.

    Uses SHA-256 of the provided key as cache key to avoid storing
    plaintext keys in memory. Cache TTL is 5 minutes.
    """
    headers = event.get("headers", {})
    provided_key = headers.get("x-api-key", "")
    if not provided_key:
        return None

    # Check cache first (avoids expensive bcrypt on every request)
    cache_key = hashlib.sha256(provided_key.encode("utf-8")).hexdigest()
    cached = _auth_cache.get(cache_key)
    if cached:
        user_info, expiry = cached
        if time.time() < expiry:
            return user_info
        else:
            del _auth_cache[cache_key]

    # Cache miss: iterate keys and check bcrypt
    api_keys = config.get("apiKeys", {})

    for key_id, key_data in api_keys.items():
        stored_hash = key_data.get("hash")
        if stored_hash:
            try:
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode("utf-8")
                if bcrypt.checkpw(provided_key.encode("utf-8"), stored_hash):
                    # Cache the successful auth
                    _auth_cache[cache_key] = (key_data, time.time() + _AUTH_CACHE_TTL)
                    return key_data
            except (ValueError, TypeError) as e:
                logger.error(f"[AUTH] bcrypt check failed for key_id={key_id}: {e}")
                continue
        else:
            # Legacy plaintext key (pre-migration)
            if key_id == provided_key:
                _auth_cache[cache_key] = (key_data, time.time() + _AUTH_CACHE_TTL)
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


def find_resource(account, resource_id):
    """Find a resource by ID within an account."""
    return next((r for r in account.get("resources", []) if r["id"] == resource_id), None)


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
