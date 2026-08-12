"""
Cloud Control Panel - Admin CRUD handlers.
Account, instance, group, API key management, and cost estimation.
"""

import uuid
from datetime import datetime, timezone

import bcrypt

from ec2_ops import get_ec2_client
from utils import EC2_PRICING, db_delete, db_get, db_put, db_query, load_config_from_db, logger, response


def handle_create_account(body):
    """Create a new account."""
    acc_id = body.get("id")
    if not acc_id:
        return response(400, {"error": "id is required"})
    meta = {k: v for k, v in body.items() if k not in ("instances", "groups", "id")}
    meta.setdefault("features", {"scheduler": True, "notifications": True, "costEstimate": True})
    db_put({"PK": "CONFIG", "SK": f"ACCOUNT#{acc_id}", "data": meta})
    return response(200, {"message": f"Account {acc_id} created", "id": acc_id})


def handle_delete_account(account_id):
    """Delete an account and all its sub-items."""
    items = db_query(f"ACCOUNT#{account_id}")
    for item in items:
        db_delete(item["PK"], item["SK"])
    db_delete("CONFIG", f"ACCOUNT#{account_id}")
    return response(200, {"message": f"Account {account_id} deleted"})


def handle_create_instance(account_id, body):
    """Create an instance in an account."""
    inst_id = body.get("id")
    if not inst_id:
        return response(400, {"error": "id is required"})
    db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"INSTANCE#{inst_id}", "data": body})
    return response(200, {"message": f"Instance {inst_id} created", "id": inst_id})


def handle_delete_instance(account_id, instance_id):
    """Delete an instance from an account."""
    db_delete(f"ACCOUNT#{account_id}", f"INSTANCE#{instance_id}")
    return response(200, {"message": f"Instance {instance_id} deleted"})


def handle_create_group(account_id, body):
    """Create a group in an account."""
    grp_id = body.get("id")
    if not grp_id:
        return response(400, {"error": "id is required"})
    db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"GROUP#{grp_id}", "data": body})
    return response(200, {"message": f"Group {grp_id} created", "id": grp_id})


def handle_delete_group(account_id, group_id):
    """Delete a group from an account."""
    db_delete(f"ACCOUNT#{account_id}", f"GROUP#{group_id}")
    return response(200, {"message": f"Group {group_id} deleted"})


def handle_list_keys(config):
    """List all API keys.

    Returns key metadata (name, role, accounts) but never the hash or plaintext.
    Includes a masked key_id for display (first 8 chars of the UUID).
    """
    keys = []
    for key_id, data in config.get("apiKeys", {}).items():
        # Never expose hash or original key value
        key_info = {
            "key_id": key_id,
            "key_preview": key_id[:8] + "...",
            "name": data.get("name", ""),
            "role": data.get("role", "operator"),
            "accounts": data.get("accounts", []),
        }
        if "scheduler" in data:
            key_info["scheduler"] = data["scheduler"]
        keys.append(key_info)
    return response(200, {"keys": keys})


def handle_create_key(body):
    """Create a new API key with bcrypt hashing.

    Generates a random key value (UUID4), hashes it with bcrypt,
    and stores the hash. Returns the plaintext key ONCE in the response
    (it will never be retrievable again).
    """
    # Generate a new random API key and a separate key_id
    plaintext_key = str(uuid.uuid4())
    key_id = str(uuid.uuid4())

    # Hash the plaintext key with bcrypt
    key_hash = bcrypt.hashpw(plaintext_key.encode("utf-8"), bcrypt.gensalt())

    data = {k: v for k, v in body.items() if k != "key"}
    data.setdefault("role", "operator")
    data.setdefault("accounts", [])
    data["hash"] = key_hash.decode("utf-8")

    db_put({"PK": "CONFIG", "SK": f"APIKEY#{key_id}", "data": data})
    return response(200, {
        "message": "Key created",
        "key": plaintext_key,
        "key_id": key_id,
        "note": "Save this key now. It cannot be retrieved again.",
    })


def handle_create_key_validated(body, user_info):
    """Create an API key with role-based validation."""
    target_role = body.get("role", "operator")
    if user_info.get("role") == "admin":
        if target_role != "operator":
            return response(403, {"error": "Un admin solo puede asignar rol de operador"})
    elif user_info.get("role") == "superadmin" and target_role == "superadmin":
        return response(403, {"error": "No se puede crear un superadmin desde el panel"})
    return handle_create_key(body)


def handle_delete_key(key_id, event):
    """Delete an API key by key_id with role-based restrictions.

    Keys are identified by their UUID key_id (the SK suffix).
    The caller's identity is validated via bcrypt in authenticate().
    """
    headers = event.get("headers", {})
    current_key = headers.get("x-api-key", "")

    # Load config to determine caller and target info
    config = load_config_from_db()

    # Find caller info by checking which key matches via bcrypt
    caller_info = None
    caller_key_id = None
    for kid, kdata in config.get("apiKeys", {}).items():
        stored_hash = kdata.get("hash")
        if stored_hash:
            try:
                hash_bytes = stored_hash.encode("utf-8") if isinstance(stored_hash, str) else stored_hash
                if bcrypt.checkpw(current_key.encode("utf-8"), hash_bytes):
                    caller_info = kdata
                    caller_key_id = kid
                    break
            except (ValueError, TypeError):
                continue
        elif kid == current_key:
            # Legacy plaintext fallback
            caller_info = kdata
            caller_key_id = kid
            break

    if not caller_info:
        return response(401, {"error": "Unauthorized"})

    # Prevent self-deletion
    if key_id == caller_key_id:
        return response(400, {"error": "No puedes eliminar tu propia API Key."})

    caller_role = caller_info.get("role", "operator")

    # Find target key info
    target_item = db_get("CONFIG", f"APIKEY#{key_id}")
    if not target_item:
        return response(404, {"error": "Key no encontrada"})
    target_info = target_item.get("data", {})
    target_role = target_info.get("role", "operator")

    if caller_role == "operator":
        return response(403, {"error": "Operadores no pueden eliminar API Keys."})

    if caller_role == "admin" and target_role != "operator":
        return response(403, {"error": "Un admin solo puede eliminar operadores."})

    if caller_role == "superadmin" and target_role == "superadmin":
        return response(403, {"error": "No puedes eliminar a otro superadmin."})

    db_delete("CONFIG", f"APIKEY#{key_id}")
    return response(200, {"message": "Key deleted"})


def handle_update_key_accounts(key_id, body):
    """Update the accounts list for a specific key."""
    item = db_get("CONFIG", f"APIKEY#{key_id}")
    if not item:
        return response(404, {"error": "Key no encontrada"})

    data = item.get("data", {})
    data["accounts"] = body.get("accounts", data.get("accounts", []))
    db_put({"PK": "CONFIG", "SK": f"APIKEY#{key_id}", "data": data})
    return response(200, {"message": "Acceso actualizado", "accounts": data["accounts"]})


def handle_get_costs(account, user_info):
    """Get cost estimation for an account."""
    features = account.get("features", {})
    if not features.get("costEstimate", False):
        return response(200, {"enabled": False, "costs": []})

    ec2 = get_ec2_client(account)
    instances = account.get("instances", [])
    instance_ids = [inst["instanceId"] for inst in instances if inst.get("instanceId")]

    if not instance_ids:
        return response(200, {"enabled": True, "costs": [], "totalCost": 0, "totalProjection": 0, "currency": "USD"})

    live_data = {}
    try:
        desc = ec2.describe_instances(InstanceIds=instance_ids)
        for res in desc.get("Reservations", []):
            for inst in res.get("Instances", []):
                live_data[inst["InstanceId"]] = {
                    "state": inst["State"]["Name"],
                    "launchTime": inst.get("LaunchTime"),
                    "instanceType": inst.get("InstanceType", "t3.medium"),
                }
    except Exception as e:
        logger.error(f"[COSTS] describe_instances failed: {e}")

    now = datetime.now(timezone.utc)
    days_elapsed = max(now.day, 1)
    costs = []
    total_cost = 0

    for inst in instances:
        live = live_data.get(inst.get("instanceId", ""), {})
        instance_type = live.get("instanceType", "t3.medium")
        hourly_rate = EC2_PRICING.get(instance_type, 0.0416)
        uptime_hours = 0
        if live.get("state") == "running" and live.get("launchTime"):
            delta = now - live["launchTime"]
            uptime_hours = delta.total_seconds() / 3600
        cost = uptime_hours * hourly_rate
        total_cost += cost
        projection = (cost / days_elapsed) * 30 if days_elapsed > 0 else 0
        costs.append({"id": inst["id"], "name": inst.get("name", inst["id"]),
            "instanceType": instance_type, "hourlyRate": hourly_rate,
            "uptimeHours": round(uptime_hours, 1), "costThisMonth": round(cost, 2),
            "projection": round(projection, 2)})

    total_projection = (total_cost / days_elapsed) * 30 if days_elapsed > 0 else 0
    return response(200, {"enabled": True, "month": now.strftime("%B %Y"), "daysElapsed": days_elapsed,
        "costs": costs, "totalCost": round(total_cost, 2),
        "totalProjection": round(total_projection, 2), "currency": "USD"})
