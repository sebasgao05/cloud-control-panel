"""
Cloud Control Panel - Authentication and authorization helpers.
"""


def authenticate(event, config):
    """Authenticate request via x-api-key header."""
    headers = event.get("headers", {})
    provided_key = headers.get("x-api-key", "")
    return config.get("apiKeys", {}).get(provided_key)


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
