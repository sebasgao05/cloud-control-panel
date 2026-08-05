"""
Cloud Control Panel - Lambda handler with DynamoDB config store.
Supports: multi-account, scheduler, notifications, cost estimation, admin config management.
"""

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from urllib import request as urllib_request
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "us-east-1")
CONFIG_TABLE = os.environ.get("CONFIG_TABLE", "cloud-control-config-ccp-main")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB resource (reused across invocations)
_ddb = None
_table = None


def get_table():
    global _ddb, _table
    if _table is None:
        _ddb = boto3.resource("dynamodb", region_name=REGION)
        _table = _ddb.Table(CONFIG_TABLE)
    return _table


# EC2 pricing (On-Demand, us-east-1, Linux, USD/hour)
EC2_PRICING = {
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208,
    "t3.medium": 0.0416, "t3.large": 0.0832, "t3.xlarge": 0.1664,
    "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464,
    "t2.large": 0.0928, "m5.large": 0.096, "m5.xlarge": 0.192,
    "r5.large": 0.126, "r5.xlarge": 0.252, "c5.large": 0.085,
    "c5.xlarge": 0.17,
}


# ─── DynamoDB Config Layer ───────────────────────────────────────────────

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
    # Get settings
    settings_item = db_get("CONFIG", "SETTINGS")
    settings = decimal_to_native(settings_item.get("data", {})) if settings_item else {
        "defaultRegion": "us-east-1", "pollIntervalSeconds": 30, "timezone": "America/Bogota"
    }

    # Get API keys
    key_items = db_query("CONFIG", "APIKEY#")
    api_keys = {}
    for item in key_items:
        key_id = item["SK"].replace("APIKEY#", "")
        data = decimal_to_native(item.get("data", {}))
        api_keys[key_id] = data

    # Get accounts
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

    # Get instances for each account
    for acc_id in account_map:
        inst_items = db_query(f"ACCOUNT#{acc_id}", "INSTANCE#")
        account_map[acc_id]["instances"] = [decimal_to_native(i.get("data", {})) for i in inst_items]
        grp_items = db_query(f"ACCOUNT#{acc_id}", "GROUP#")
        account_map[acc_id]["groups"] = [decimal_to_native(g.get("data", {})) for g in grp_items]
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
    table = get_table()

    # Settings
    db_put({"PK": "CONFIG", "SK": "SETTINGS", "data": json_config.get("settings", {})})

    # API Keys
    for key_id, key_data in json_config.get("apiKeys", {}).items():
        db_put({"PK": "CONFIG", "SK": f"APIKEY#{key_id}", "data": key_data})

    # Accounts
    for acc in json_config.get("accounts", []):
        acc_id = acc["id"]
        acc_meta = {k: v for k, v in acc.items() if k not in ("instances", "groups", "schedule", "notifications", "id")}
        db_put({"PK": "CONFIG", "SK": f"ACCOUNT#{acc_id}", "data": acc_meta})

        # Instances
        for inst in acc.get("instances", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"INSTANCE#{inst['id']}", "data": inst})

        # Groups
        for grp in acc.get("groups", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"GROUP#{grp['id']}", "data": grp})

        # Schedule rules
        for rule in acc.get("schedule", {}).get("rules", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"SCHEDULE#{rule['id']}", "data": rule})

        # Notification channels
        for ch in acc.get("notifications", {}).get("channels", []):
            db_put({"PK": f"ACCOUNT#{acc_id}", "SK": f"CHANNEL#{ch['id']}", "data": ch})

    logger.info("[MIGRATE] JSON config migrated to DynamoDB successfully")


# ─── EC2 Clients ─────────────────────────────────────────────────────────

def get_ec2_client(account):
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)
    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="CloudControlPanel")["Credentials"]
        return boto3.client("ec2", region_name=region, aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"], aws_session_token=creds["SessionToken"])
    return boto3.client("ec2", region_name=region)


def get_ssm_client(account):
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)
    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="CloudControlPanel")["Credentials"]
        return boto3.client("ssm", region_name=region, aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"], aws_session_token=creds["SessionToken"])
    return boto3.client("ssm", region_name=region)


# ─── Auth & Helpers ──────────────────────────────────────────────────────

def authenticate(event, config):
    headers = event.get("headers", {})
    provided_key = headers.get("x-api-key", "")
    return config.get("apiKeys", {}).get(provided_key)


def get_allowed_accounts(user_info, config):
    all_accounts = config.get("accounts", [])
    allowed = user_info.get("accounts", [])
    if "*" in allowed:
        return all_accounts
    return [acc for acc in all_accounts if acc["id"] in allowed]


def find_instance(account, instance_id):
    return next((i for i in account.get("instances", []) if i["id"] == instance_id), None)


def find_group(account, group_id):
    return next((g for g in account.get("groups", []) if g["id"] == group_id), None)


def get_scheduler_permissions(user_info):
    if user_info.get("role") == "superadmin":
        return {"view": True, "edit": True}
    # Only superadmin can manage scheduler now
    # Admin and operators can only view if explicitly granted
    if user_info.get("role") == "admin":
        return {"view": False, "edit": False}
    sched = user_info.get("scheduler", {})
    can_edit = sched.get("edit", False)
    return {"view": can_edit or sched.get("view", False), "edit": can_edit}


def is_admin(user_info):
    return user_info.get("role") in ("admin", "superadmin")


def is_superadmin(user_info):
    return user_info.get("role") == "superadmin"


# ─── Lambda Handler (Router) ─────────────────────────────────────────────

def lambda_handler(event, context):
    # ─── Handle EventBridge Scheduler invocation ────────────────────────
    if event.get("source") == "scheduler":
        return handle_scheduler_event(event)

    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    raw_path = event.get("rawPath", "/")
    stage = event.get("requestContext", {}).get("stage", "")
    if stage and stage != "$default" and raw_path.startswith(f"/{stage}"):
        path = raw_path[len(f"/{stage}"):]
    else:
        path = raw_path
    if not path:
        path = "/"

    # Auto-migrate: if DynamoDB is empty, load from bundled JSON
    if not is_db_initialized():
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                json_config = json.load(f)
            migrate_json_to_db(json_config)
            logger.info("[INIT] Auto-migrated JSON config to DynamoDB")

    config = load_config_from_db()

    # Special admin routes that don't need account context
    parts = path.strip("/").split("/")

    # POST /api/migrate (force re-migrate from JSON)
    if method == "POST" and parts == ["api", "migrate"]:
        user_info = authenticate(event, config)
        if not user_info or user_info.get("role") != "superadmin":
            # Allow admin too for initial setup
            if not user_info or not is_admin(user_info):
                return response(401, {"error": "Unauthorized"})
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                migrate_json_to_db(json.load(f))
        return response(200, {"message": "Config migrated from JSON"})

    user_info = authenticate(event, config)
    if not user_info:
        return response(401, {"error": "Unauthorized"})

    try:
        # GET /api/accounts
        if method == "GET" and parts == ["api", "accounts"]:
            return handle_list_accounts(user_info, config)

        # GET /api/config (superadmin: full config export)
        if method == "GET" and parts == ["api", "config"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin"})
            return response(200, config)

        # PUT /api/config (superadmin: full config import)
        if method == "PUT" and parts == ["api", "config"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin"})
            body = json.loads(event.get("body", "{}") or "{}")
            migrate_json_to_db(body)
            return response(200, {"message": "Config imported successfully"})

        # POST /api/accounts (superadmin: create account)
        if method == "POST" and parts == ["api", "accounts"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede crear cuentas"})
            body = json.loads(event.get("body", "{}") or "{}")
            return handle_create_account(body)

        # DELETE /api/accounts/{id} (superadmin)
        if method == "DELETE" and len(parts) == 3 and parts[0] == "api" and parts[1] == "accounts":
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede eliminar cuentas"})
            return handle_delete_account(parts[2])

        # /api/accounts/{accountId}/...
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "accounts":
            account_id = parts[2]
            allowed_accounts = get_allowed_accounts(user_info, config)
            account = next((a for a in allowed_accounts if a["id"] == account_id), None)
            if not account:
                return response(403, {"error": "Access denied"})

            # GET /api/accounts/{id}/instances
            if len(parts) == 4 and parts[3] == "instances" and method == "GET":
                return handle_list_instances(account)

            # POST /api/accounts/{id}/instances (superadmin: add instance)
            if len(parts) == 4 and parts[3] == "instances" and method == "POST":
                if not is_superadmin(user_info):
                    return response(403, {"error": "Solo superadmin puede crear instancias"})
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_create_instance(account_id, body)

            # /api/accounts/{id}/instances/{iid}/...
            if len(parts) >= 5 and parts[3] == "instances":
                instance = find_instance(account, parts[4])
                if not instance:
                    return response(404, {"error": "Instance not found"})
                if len(parts) == 5 and method == "DELETE":
                    if not is_superadmin(user_info):
                        return response(403, {"error": "Solo superadmin puede eliminar instancias"})
                    return handle_delete_instance(account_id, parts[4])
                if len(parts) == 6:
                    action = parts[5]
                    if method == "GET" and action == "status":
                        return handle_instance_status(account, instance)
                    if method == "POST" and action == "start":
                        return handle_instance_start(account, instance, user_info)
                    if method == "POST" and action == "stop":
                        return handle_instance_stop(account, instance, user_info)
                    if method == "POST" and action == "update":
                        return handle_instance_update(account, instance, user_info)
                    if method == "GET" and action == "dashboard-url":
                        return handle_dashboard_url(account, instance)

            # /api/accounts/{id}/groups/...
            if len(parts) >= 4 and parts[3] == "groups":
                if len(parts) == 4 and method == "POST":
                    if not is_superadmin(user_info):
                        return response(403, {"error": "Solo superadmin puede crear grupos"})
                    body = json.loads(event.get("body", "{}") or "{}")
                    return handle_create_group(account_id, body)
                if len(parts) >= 5:
                    group = find_group(account, parts[4])
                    if len(parts) == 5 and method == "DELETE":
                        if not is_superadmin(user_info):
                            return response(403, {"error": "Solo superadmin puede eliminar grupos"})
                        return handle_delete_group(account_id, parts[4])
                    if not group:
                        return response(404, {"error": "Group not found"})
                    if len(parts) == 6:
                        action = parts[5]
                        if method == "GET" and action == "status":
                            return handle_group_status(account, group)
                        if method == "POST" and action == "start":
                            return handle_group_start(account, group, user_info)
                        if method == "POST" and action == "stop":
                            return handle_group_stop(account, group, user_info)

            # Schedule endpoints
            if len(parts) == 4 and parts[3] == "schedule" and method == "GET":
                return handle_get_schedule(account, user_info)
            if len(parts) == 4 and parts[3] == "schedule" and method == "PUT":
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_update_schedule(account, account_id, user_info, body)

            # Notifications endpoints
            if len(parts) == 4 and parts[3] == "notifications" and method == "GET":
                return handle_get_notifications(account, user_info)
            if len(parts) == 4 and parts[3] == "notifications" and method == "PUT":
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_update_notifications(account, account_id, user_info, body)
            if len(parts) == 5 and parts[3] == "notifications" and parts[4] == "test" and method == "POST":
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_test_notification(account, user_info, body)

            # Costs endpoint
            if len(parts) == 4 and parts[3] == "costs" and method == "GET":
                return handle_get_costs(account, user_info)

            # Activity endpoints
            if len(parts) == 4 and parts[3] == "activity" and method == "GET":
                return handle_get_activity(account_id)
            if len(parts) == 4 and parts[3] == "activity" and method == "DELETE":
                if not is_admin(user_info):
                    return response(403, {"error": "Admin only"})
                return handle_clear_activity(account_id)

        # API Keys management
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "keys":
            if method == "GET" and len(parts) == 3 and parts[2] == "list":
                if not is_admin(user_info):
                    return response(403, {"error": "Admin only"})
                return handle_list_keys(config)
            if method == "POST" and len(parts) == 3 and parts[2] == "create":
                if not is_admin(user_info):
                    return response(403, {"error": "Solo admin o superadmin puede crear API Keys"})
                body = json.loads(event.get("body", "{}") or "{}")
                target_role = body.get("role", "operator")

                if user_info.get("role") == "admin":
                    # Admin can only create/edit operators and cannot change role to non-operator
                    existing = db_get("CONFIG", f"APIKEY#{body.get('key', '')}")
                    if existing:
                        existing_role = existing.get("data", {}).get("role", "operator")
                        if existing_role != "operator":
                            return response(403, {"error": "Un admin solo puede editar operadores"})
                    # Admin cannot assign role other than operator
                    if target_role != "operator":
                        return response(403, {"error": "Un admin solo puede asignar rol de operador"})
                elif user_info.get("role") == "superadmin":
                    # Superadmin cannot create another superadmin via this endpoint
                    if target_role == "superadmin":
                        return response(403, {"error": "No se puede crear un superadmin desde el panel"})

                return handle_create_key(body)
            # PUT /api/keys/{id}/accounts - update key accounts (superadmin only)
            if method == "PUT" and len(parts) == 4 and parts[3] == "accounts":
                if not is_superadmin(user_info):
                    return response(403, {"error": "Solo superadmin"})
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_update_key_accounts(parts[2], body)
            if method == "DELETE" and len(parts) == 3:
                return handle_delete_key(parts[2], event)

        return response(404, {"error": "Not found"})

    except Exception as e:
        logger.error(f"[ERROR] {str(e)}", exc_info=True)
        return response(500, {"error": str(e)})


# ─── Admin CRUD Handlers ─────────────────────────────────────────────────

def handle_create_account(body):
    acc_id = body.get("id")
    if not acc_id:
        return response(400, {"error": "id is required"})
    meta = {k: v for k, v in body.items() if k not in ("instances", "groups", "id")}
    meta.setdefault("features", {"scheduler": True, "notifications": True, "costEstimate": True})
    db_put({"PK": "CONFIG", "SK": f"ACCOUNT#{acc_id}", "data": meta})
    return response(200, {"message": f"Account {acc_id} created", "id": acc_id})


def handle_delete_account(account_id):
    # Delete account and all its sub-items
    items = db_query(f"ACCOUNT#{account_id}")
    for item in items:
        db_delete(item["PK"], item["SK"])
    db_delete("CONFIG", f"ACCOUNT#{account_id}")
    return response(200, {"message": f"Account {account_id} deleted"})


def handle_create_instance(account_id, body):
    inst_id = body.get("id")
    if not inst_id:
        return response(400, {"error": "id is required"})
    db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"INSTANCE#{inst_id}", "data": body})
    return response(200, {"message": f"Instance {inst_id} created", "id": inst_id})


def handle_delete_instance(account_id, instance_id):
    db_delete(f"ACCOUNT#{account_id}", f"INSTANCE#{instance_id}")
    return response(200, {"message": f"Instance {instance_id} deleted"})


def handle_create_group(account_id, body):
    grp_id = body.get("id")
    if not grp_id:
        return response(400, {"error": "id is required"})
    db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"GROUP#{grp_id}", "data": body})
    return response(200, {"message": f"Group {grp_id} created", "id": grp_id})


def handle_delete_group(account_id, group_id):
    db_delete(f"ACCOUNT#{account_id}", f"GROUP#{group_id}")
    return response(200, {"message": f"Group {group_id} deleted"})


def handle_list_keys(config):
    keys = []
    for key_id, data in config.get("apiKeys", {}).items():
        keys.append({"key": key_id, **data})
    return response(200, {"keys": keys})


def handle_create_key(body):
    key_id = body.get("key")
    if not key_id:
        import uuid
        key_id = str(uuid.uuid4())
    data = {k: v for k, v in body.items() if k != "key"}
    data.setdefault("role", "operator")
    data.setdefault("accounts", [])
    db_put({"PK": "CONFIG", "SK": f"APIKEY#{key_id}", "data": data})
    return response(200, {"message": "Key created", "key": key_id})


def handle_delete_key(key_id, event):
    headers = event.get("headers", {})
    current_key = headers.get("x-api-key", "")

    # Prevent self-deletion
    if key_id == current_key:
        return response(400, {"error": "No puedes eliminar tu propia API Key."})

    # Get caller role
    config = load_config_from_db()
    caller_info = config.get("apiKeys", {}).get(current_key, {})
    caller_role = caller_info.get("role", "operator")

    # Get target role
    target_info = config.get("apiKeys", {}).get(key_id, {})
    target_role = target_info.get("role", "operator")

    # Operators cannot delete anyone
    if caller_role == "operator":
        return response(403, {"error": "Operadores no pueden eliminar API Keys."})

    # Admin can only delete operators
    if caller_role == "admin":
        if target_role != "operator":
            return response(403, {"error": "Un admin solo puede eliminar operadores."})

    # Superadmin can delete admins and operators, not other superadmins
    if caller_role == "superadmin":
        if target_role == "superadmin":
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


# ─── Instance & Group Operation Handlers ─────────────────────────────────

def handle_list_accounts(user_info, config):
    accounts = get_allowed_accounts(user_info, config)
    result = [{"id": a["id"], "name": a.get("name", a["id"]), "awsAccountId": a.get("awsAccountId", ""),
               "region": a.get("region", REGION), "instanceCount": len(a.get("instances", [])),
               "groupCount": len(a.get("groups", []))} for a in accounts]
    return response(200, {"accounts": result, "user": user_info.get("name", ""), "role": user_info.get("role", "operator")})


def handle_list_instances(account):
    ec2 = get_ec2_client(account)
    instances = account.get("instances", [])
    instance_ids = [inst["instanceId"] for inst in instances if inst.get("instanceId")]

    states = {}
    if instance_ids:
        try:
            desc = ec2.describe_instances(InstanceIds=instance_ids)
            for res in desc.get("Reservations", []):
                for inst in res.get("Instances", []):
                    states[inst["InstanceId"]] = {
                        "state": inst["State"]["Name"],
                        "publicIp": inst.get("PublicIpAddress"),
                        "launchTime": inst.get("LaunchTime"),
                    }
        except Exception as e:
            logger.error(f"[EC2] describe_instances failed: {e}")

    result_instances = []
    for inst in instances:
        live = states.get(inst.get("instanceId", ""), {})
        state = live.get("state", "unknown")
        launch_time = live.get("launchTime")
        uptime = None
        if state == "running" and launch_time:
            delta = datetime.now(timezone.utc) - launch_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            uptime = f"{hours}h {remainder // 60}m"
        result_instances.append({
            "id": inst["id"], "name": inst.get("name", inst["id"]),
            "instanceId": inst.get("instanceId", ""), "description": inst.get("description", ""),
            "dashboardPort": inst.get("dashboardPort"), "group": inst.get("group"),
            "state": state, "publicIp": live.get("publicIp"), "uptime": uptime,
        })

    groups = account.get("groups", [])
    result_groups = []
    for grp in groups:
        member_ids = grp.get("startOrder", [])
        member_states = [ri["state"] for mid in member_ids for ri in result_instances if ri["id"] == mid]
        if all(s == "running" for s in member_states) and member_states:
            group_state = "running"
        elif all(s == "stopped" for s in member_states) and member_states:
            group_state = "stopped"
        else:
            group_state = "partial"
        result_groups.append({"id": grp["id"], "name": grp.get("name", grp["id"]),
            "description": grp.get("description", ""), "color": grp.get("color", "#6366f1"),
            "members": member_ids, "state": group_state})

    return response(200, {"accountId": account["id"], "accountName": account.get("name", ""),
                          "instances": result_instances, "groups": result_groups})


def handle_instance_status(account, instance):
    ec2 = get_ec2_client(account)
    desc = ec2.describe_instances(InstanceIds=[instance["instanceId"]])
    inst_data = desc["Reservations"][0]["Instances"][0]
    state = inst_data["State"]["Name"]
    launch_time = inst_data.get("LaunchTime")
    uptime = None
    if state == "running" and launch_time:
        delta = datetime.now(timezone.utc) - launch_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        uptime = f"{hours}h {remainder // 60}m"
    return response(200, {"id": instance["id"], "name": instance.get("name", ""),
        "instanceId": instance["instanceId"], "state": state,
        "publicIp": inst_data.get("PublicIpAddress"), "uptime": uptime,
        "dashboardPort": instance.get("dashboardPort"), "description": instance.get("description", ""),
        "group": instance.get("group")})


def handle_instance_start(account, instance, user_info):
    ec2 = get_ec2_client(account)
    ec2.start_instances(InstanceIds=[instance["instanceId"]])
    logger.info(f"[ACTION] user={user_info['name']} action=START instance={instance['instanceId']}")
    log_activity(account["id"], "start", user_info.get("name", "unknown"), [instance["instanceId"]])
    send_notifications(account, "started", instance.get("name", instance["id"]), user_info)
    return response(200, {"message": "Instance starting", "instanceId": instance["instanceId"]})


def handle_instance_stop(account, instance, user_info):
    ec2 = get_ec2_client(account)
    ec2.stop_instances(InstanceIds=[instance["instanceId"]])
    logger.info(f"[ACTION] user={user_info['name']} action=STOP instance={instance['instanceId']}")
    log_activity(account["id"], "stop", user_info.get("name", "unknown"), [instance["instanceId"]])
    send_notifications(account, "stopped", instance.get("name", instance["id"]), user_info)
    return response(200, {"message": "Instance stopping", "instanceId": instance["instanceId"]})


def handle_instance_update(account, instance, user_info):
    ssm = get_ssm_client(account)
    cmd = ssm.send_command(InstanceIds=[instance["instanceId"]], DocumentName="AWS-RunShellScript",
        Parameters={"commands": ['sudo -u ec2-user bash -lc "cd ~/app && git pull && bash install.sh"',
                                 "sudo systemctl restart app"], "executionTimeout": ["600"]})
    return response(200, {"message": "Update started", "commandId": cmd["Command"]["CommandId"]})


def handle_dashboard_url(account, instance):
    port = instance.get("dashboardPort")
    if not port:
        return response(200, {"url": None, "reason": "No dashboard configured"})
    ec2 = get_ec2_client(account)
    desc = ec2.describe_instances(InstanceIds=[instance["instanceId"]])
    public_ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress")
    if not public_ip:
        return response(200, {"url": None, "reason": "Instance not running"})
    return response(200, {"url": f"http://{public_ip}:{port}"})


def handle_group_status(account, group):
    ec2 = get_ec2_client(account)
    member_ids = group.get("startOrder", [])
    instance_ids, imap = [], {}
    for mid in member_ids:
        inst = find_instance(account, mid)
        if inst:
            instance_ids.append(inst["instanceId"])
            imap[inst["instanceId"]] = inst
    if not instance_ids:
        return response(200, {"group": group["id"], "members": [], "state": "empty"})
    desc = ec2.describe_instances(InstanceIds=instance_ids)
    members = []
    for res in desc.get("Reservations", []):
        for d in res.get("Instances", []):
            ci = imap.get(d["InstanceId"], {})
            members.append({"id": ci.get("id"), "name": ci.get("name"), "instanceId": d["InstanceId"],
                           "state": d["State"]["Name"], "publicIp": d.get("PublicIpAddress")})
    states = [m["state"] for m in members]
    gs = "running" if all(s == "running" for s in states) else "stopped" if all(s == "stopped" for s in states) else "partial"
    return response(200, {"group": group["id"], "name": group.get("name"), "state": gs, "members": members})


def handle_group_start(account, group, user_info):
    ec2 = get_ec2_client(account)
    started = []
    for mid in group.get("startOrder", []):
        inst = find_instance(account, mid)
        if inst:
            ec2.start_instances(InstanceIds=[inst["instanceId"]])
            started.append({"id": inst["id"], "name": inst.get("name")})
    send_notifications(account, "started", f"Grupo {group.get('name')}", user_info)
    return response(200, {"message": "Group starting", "group": group["id"], "started": started})


def handle_group_stop(account, group, user_info):
    ec2 = get_ec2_client(account)
    stopped = []
    for mid in group.get("stopOrder", []):
        inst = find_instance(account, mid)
        if inst:
            ec2.stop_instances(InstanceIds=[inst["instanceId"]])
            stopped.append({"id": inst["id"], "name": inst.get("name")})
    send_notifications(account, "stopped", f"Grupo {group.get('name')}", user_info)
    return response(200, {"message": "Group stopping", "group": group["id"], "stopped": stopped})


# ─── Scheduler Handlers ──────────────────────────────────────────────────

def handle_get_schedule(account, user_info):
    permissions = get_scheduler_permissions(user_info)
    features = account.get("features", {})
    if not features.get("scheduler", False):
        return response(200, {"enabled": False, "permissions": {"view": False, "edit": False}, "schedule": None})
    if not permissions["view"]:
        return response(200, {"enabled": True, "permissions": {"view": False, "edit": False}, "schedule": None})
    schedule = account.get("schedule", {"timezone": "America/Bogota", "rules": []})
    instance_map = {inst["id"]: inst.get("name", inst["id"]) for inst in account.get("instances", [])}
    return response(200, {"enabled": True, "permissions": permissions, "schedule": schedule, "instanceMap": instance_map})


def handle_update_schedule(account, account_id, user_info, body):
    permissions = get_scheduler_permissions(user_info)
    if not permissions["edit"]:
        return response(200, {"error": "No tienes permiso", "denied": True})

    # Delete existing rules from DynamoDB
    existing = db_query(f"ACCOUNT#{account_id}", "SCHEDULE#")
    old_rule_ids = [item["SK"].replace("SCHEDULE#", "") for item in existing]
    for item in existing:
        db_delete(item["PK"], item["SK"])

    # Delete old EventBridge schedules
    for old_id in old_rule_ids:
        delete_eventbridge_schedule(account_id, old_id, "start")
        delete_eventbridge_schedule(account_id, old_id, "stop")

    # Create new rules in DynamoDB + EventBridge
    tz = body.get("timezone", account.get("schedule", {}).get("timezone", "America/Bogota"))
    for rule in body.get("rules", []):
        if not rule.get("id"):
            rule["id"] = f"rule-{int(datetime.now().timestamp())}"
        db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"SCHEDULE#{rule['id']}", "data": rule})

        if rule.get("enabled", True):
            create_eventbridge_schedule(account_id, account, rule, tz)

    # Notify about schedule update
    send_notifications(account, "scheduler_executed", f"Programacion actualizada por {user_info.get('name', 'admin')}")

    return response(200, {"message": "Programacion actualizada y schedules creados en AWS"})


# ─── Activity Log ─────────────────────────────────────────────────────────

def log_activity(account_id, action, user_name, instance_ids, rule_id=None):
    """Log an activity event to DynamoDB."""
    ts = datetime.now(timezone.utc).isoformat()
    entry = {
        "action": action,
        "user": user_name,
        "instanceIds": instance_ids,
        "timestamp": ts,
    }
    if rule_id:
        entry["ruleId"] = rule_id
    db_put({"PK": f"ACTIVITY#{account_id}", "SK": ts, "data": entry})


def handle_get_activity(account_id):
    """Get activity log for an account (last 50 entries)."""
    items = db_query(f"ACTIVITY#{account_id}")
    # Sort by SK (timestamp) descending, limit 50
    items.sort(key=lambda x: x["SK"], reverse=True)
    entries = [decimal_to_native(i.get("data", {})) for i in items[:50]]
    return response(200, {"activities": entries})


def handle_clear_activity(account_id):
    """Clear all activity logs for an account."""
    items = db_query(f"ACTIVITY#{account_id}")
    for item in items:
        db_delete(item["PK"], item["SK"])
    return response(200, {"message": "Actividad eliminada"})


# ─── EventBridge Scheduler Event Handler ─────────────────────────────────

def handle_scheduler_event(event):
    """Handle scheduled start/stop invoked by EventBridge Scheduler."""
    action = event.get("action")  # "start" or "stop"
    account_id = event.get("accountId")
    instance_ids = event.get("instanceIds", [])
    rule_id = event.get("ruleId", "unknown")

    if not action or not account_id or not instance_ids:
        logger.error(f"[SCHEDULER EVENT] Invalid payload: {json.dumps(event)}")
        return {"statusCode": 400, "body": "Invalid scheduler event"}

    config = load_config_from_db()
    account = next((a for a in config.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        logger.error(f"[SCHEDULER EVENT] Account {account_id} not found")
        return {"statusCode": 404, "body": "Account not found"}

    ec2 = get_ec2_client(account)
    valid_ids = [iid for iid in instance_ids if iid]

    if not valid_ids:
        return {"statusCode": 200, "body": "No valid instance IDs"}

    try:
        if action == "start":
            ec2.start_instances(InstanceIds=valid_ids)
            msg = f"Scheduler encendio: {', '.join(valid_ids)}"
        elif action == "stop":
            ec2.stop_instances(InstanceIds=valid_ids)
            msg = f"Scheduler apago: {', '.join(valid_ids)}"
        else:
            return {"statusCode": 400, "body": f"Unknown action: {action}"}

        logger.info(f"[SCHEDULER EVENT] {action.upper()} instances={valid_ids} account={account_id} rule={rule_id}")

        # Log activity to DynamoDB
        log_activity(account_id, action, "Scheduler", valid_ids, rule_id)

        # Send notifications with scheduler user info
        scheduler_user = {"name": "Scheduler Automatico", "role": "scheduler"}
        send_notifications(account, "scheduler_executed", msg, scheduler_user)

    except Exception as e:
        logger.error(f"[SCHEDULER EVENT] Error: {e}")
        send_notifications(account, "error", f"Scheduler error ({action}): {str(e)}")
        return {"statusCode": 500, "body": str(e)}

    return {"statusCode": 200, "body": f"{action} executed for {len(valid_ids)} instances"}


# ─── EventBridge Scheduler Integration ───────────────────────────────────

def cron_to_eventbridge(cron_expr, tz):
    """Convert '0 7 * * 1-5' to EventBridge format 'cron(0 7 ? * MON-FRI *)'."""
    parts = cron_expr.split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts

    # Convert day-of-week numbers to EventBridge format
    day_map = {"0": "SUN", "1": "MON", "2": "TUE", "3": "WED", "4": "THU", "5": "FRI", "6": "SAT", "7": "SUN"}

    def convert_dow(d):
        # Handle ranges like 1-5
        if "-" in d:
            start, end = d.split("-")
            return f"{day_map.get(start, start)}-{day_map.get(end, end)}"
        if "," in d:
            return ",".join(day_map.get(x.strip(), x.strip()) for x in d.split(","))
        return day_map.get(d, d)

    eb_dow = convert_dow(dow)
    # EventBridge cron: minute hour day-of-month month day-of-week year
    # When DOW is specified, DOM must be '?'
    return f"cron({minute} {hour} ? {month} {eb_dow} *)"


def create_eventbridge_schedule(account_id, account, rule, tz):
    """Create start and stop EventBridge schedules for a rule."""
    scheduler = boto3.client("scheduler", region_name=REGION)
    lambda_arn = os.environ.get("LAMBDA_ARN", "")
    role_arn = os.environ.get("SCHEDULER_ROLE_ARN", "")
    stack_tag = os.environ.get("STACK_TAG", "ccp-main")

    if not lambda_arn or not role_arn:
        logger.warning("[SCHEDULER] Missing LAMBDA_ARN or SCHEDULER_ROLE_ARN")
        return

    instances = rule.get("instances", [])
    rule_id = rule["id"]

    # Resolve instance IDs from config IDs
    instance_ec2_ids = []
    for inst_config_id in instances:
        for inst in account.get("instances", []):
            if inst["id"] == inst_config_id:
                instance_ec2_ids.append(inst.get("instanceId", ""))
                break

    # Create START schedule
    start_cron = cron_to_eventbridge(rule.get("startCron", ""), tz)
    if start_cron:
        try:
            scheduler.create_schedule(
                Name=f"{stack_tag}-{account_id}-{rule_id}-start",
                GroupName="default",
                ScheduleExpression=start_cron,
                ScheduleExpressionTimezone=tz,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler",
                        "action": "start",
                        "accountId": account_id,
                        "instanceIds": instance_ec2_ids,
                        "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )
            logger.info(f"[SCHEDULER] Created start schedule for {rule_id}")
        except scheduler.exceptions.ConflictException:
            # Schedule already exists, update it
            scheduler.update_schedule(
                Name=f"{stack_tag}-{account_id}-{rule_id}-start",
                GroupName="default",
                ScheduleExpression=start_cron,
                ScheduleExpressionTimezone=tz,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler",
                        "action": "start",
                        "accountId": account_id,
                        "instanceIds": instance_ec2_ids,
                        "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )

    # Create STOP schedule
    stop_cron = cron_to_eventbridge(rule.get("stopCron", ""), tz)
    if stop_cron:
        try:
            scheduler.create_schedule(
                Name=f"{stack_tag}-{account_id}-{rule_id}-stop",
                GroupName="default",
                ScheduleExpression=stop_cron,
                ScheduleExpressionTimezone=tz,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler",
                        "action": "stop",
                        "accountId": account_id,
                        "instanceIds": instance_ec2_ids,
                        "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )
            logger.info(f"[SCHEDULER] Created stop schedule for {rule_id}")
        except scheduler.exceptions.ConflictException:
            scheduler.update_schedule(
                Name=f"{stack_tag}-{account_id}-{rule_id}-stop",
                GroupName="default",
                ScheduleExpression=stop_cron,
                ScheduleExpressionTimezone=tz,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler",
                        "action": "stop",
                        "accountId": account_id,
                        "instanceIds": instance_ec2_ids,
                        "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )


def delete_eventbridge_schedule(account_id, rule_id, action_type):
    """Delete an EventBridge schedule."""
    scheduler = boto3.client("scheduler", region_name=REGION)
    stack_tag = os.environ.get("STACK_TAG", "ccp-main")
    name = f"{stack_tag}-{account_id}-{rule_id}-{action_type}"
    try:
        scheduler.delete_schedule(Name=name, GroupName="default")
        logger.info(f"[SCHEDULER] Deleted schedule {name}")
    except Exception:
        pass  # Schedule may not exist


# ─── Notifications Handlers ──────────────────────────────────────────────

def handle_get_notifications(account, user_info):
    features = account.get("features", {})
    if not features.get("notifications", False):
        return response(200, {"enabled": False, "canEdit": False, "channels": []})
    if not is_superadmin(user_info):
        return response(200, {"enabled": True, "canEdit": False, "channels": []})
    channels = account.get("notifications", {}).get("channels", [])
    return response(200, {"enabled": True, "canEdit": True, "channels": channels})


def handle_update_notifications(account, account_id, user_info, body):
    if not is_superadmin(user_info):
        return response(200, {"error": "Solo superadmin", "denied": True})
    # Delete existing channels and write new ones
    existing = db_query(f"ACCOUNT#{account_id}", "CHANNEL#")
    for item in existing:
        db_delete(item["PK"], item["SK"])
    for ch in body.get("channels", []):
        if not ch.get("id"):
            ch["id"] = f"ch-{int(datetime.now().timestamp())}"
        db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"CHANNEL#{ch['id']}", "data": ch})
    return response(200, {"message": "Notificaciones actualizadas"})


def handle_test_notification(account, user_info, body):
    if not is_superadmin(user_info):
        return response(200, {"error": "Solo superadmin", "denied": True})
    channel_id = body.get("channelId")
    channels = account.get("notifications", {}).get("channels", [])
    channel = next((ch for ch in channels if ch["id"] == channel_id), None)
    if not channel:
        return response(200, {"error": "Canal no encontrado"})
    success = send_single_notification(channel, "test", "Notificacion de prueba - Cloud Control Panel", "Cloud Control Panel - Test")
    if success:
        return response(200, {"message": f"Prueba enviada a {channel.get('name')}"})
    return response(200, {"error": f"Error enviando a {channel.get('name')}"})


def send_notifications(account, event, instance_name, user_info=None):
    features = account.get("features", {})
    if not features.get("notifications", False):
        return
    # Build detailed message
    user_name = user_info.get("name", "Sistema") if user_info else "Sistema"
    user_role = user_info.get("role", "unknown") if user_info else "scheduler"
    account_name = account.get("name", account.get("id", ""))

    event_labels = {"started": "ENCENDIDO", "stopped": "APAGADO", "error": "ERROR", "scheduler_executed": "SCHEDULER"}
    event_label = event_labels.get(event, event.upper())

    subject = f"[Cloud Control] {event_label}: {instance_name}"
    body = (
        f"🔔 {event_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Recurso: {instance_name}\n"
        f"Cuenta: {account_name}\n"
        f"Ejecutado por: {user_name} ({user_role})\n"
        f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Cloud Control Panel"
    )

    for ch in account.get("notifications", {}).get("channels", []):
        if not ch.get("enabled"):
            continue
        if event not in ch.get("events", []):
            continue
        try:
            send_single_notification(ch, event, body, subject)
        except Exception as e:
            logger.error(f"[NOTIFY ERROR] {ch.get('type')} {ch.get('name')}: {e}")


def send_single_notification(channel, event, message, subject=None):
    ch_type = channel.get("type")
    config = channel.get("config", {})
    try:
        if ch_type == "email":
            return send_email(config, message, subject)
        elif ch_type == "telegram":
            return send_telegram(config, message)
        elif ch_type == "teams":
            return send_teams(config, message)
    except Exception as e:
        logger.error(f"[NOTIFY] {ch_type} failed: {e}")
    return False


def send_email(config, message, subject=None):
    to_addr = config.get("to")
    if not to_addr:
        return False
    msg = MIMEText(message)
    msg["Subject"] = subject or "Cloud Control Panel - Alerta"
    msg["From"] = config.get("smtpUser", "noreply@cloudcontrol.local")
    msg["To"] = to_addr
    with smtplib.SMTP(config.get("smtpHost", "smtp.gmail.com"), int(config.get("smtpPort", 587)), timeout=10) as s:
        s.starttls()
        if config.get("smtpUser") and config.get("smtpPass"):
            s.login(config["smtpUser"], config["smtpPass"])
        s.sendmail(msg["From"], [to_addr], msg.as_string())
    return True


def send_telegram(config, message):
    bot_token = config.get("botToken")
    chat_id = config.get("chatId")
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = urllib_request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib_request.urlopen(req, timeout=10)
    return True


def send_teams(config, message):
    webhook_url = config.get("webhookUrl")
    if not webhook_url:
        return False
    data = json.dumps({"text": message}).encode()
    req = urllib_request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
    urllib_request.urlopen(req, timeout=10)
    return True


# ─── Cost Estimation ─────────────────────────────────────────────────────

def handle_get_costs(account, user_info):
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


# ─── Response Helper ─────────────────────────────────────────────────────

def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
        },
        "body": json.dumps(body, default=str),
    }
