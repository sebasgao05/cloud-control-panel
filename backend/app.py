"""Cloud Control Panel - Lambda handler (router). Entry point: app.lambda_handler."""
import json
import os

from admin import (handle_create_account, handle_create_group, handle_create_instance,
    handle_create_key_validated, handle_delete_account, handle_delete_group,
    handle_delete_instance, handle_delete_key, handle_get_costs, handle_list_keys, handle_update_key_accounts)
from auth import authenticate, find_group, find_instance, get_allowed_accounts, is_admin, is_superadmin
from ec2_ops import (handle_dashboard_url, handle_group_start, handle_group_status, handle_group_stop,
    handle_instance_start, handle_instance_status, handle_instance_stop, handle_instance_update,
    handle_list_accounts, handle_list_instances)
from notifications import handle_get_notifications, handle_test_notification, handle_update_notifications
from scheduler import (handle_clear_activity, handle_get_activity, handle_get_schedule,
    handle_scheduler_event, handle_update_schedule)
from utils import CONFIG_PATH, is_db_initialized, load_config_from_db, logger, migrate_json_to_db, response


def lambda_handler(event, context):
    """Main Lambda entry point - routes requests to handler modules."""
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
    if not is_db_initialized():
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                migrate_json_to_db(json.load(f))
            logger.info("[INIT] Auto-migrated JSON config to DynamoDB")
    config = load_config_from_db()
    parts = path.strip("/").split("/")
    if method == "POST" and parts == ["api", "migrate"]:
        user_info = authenticate(event, config)
        if not user_info or (user_info.get("role") != "superadmin" and not is_admin(user_info)):
            return response(401, {"error": "Unauthorized"})
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                migrate_json_to_db(json.load(f))
        return response(200, {"message": "Config migrated from JSON"})
    user_info = authenticate(event, config)
    if not user_info:
        return response(401, {"error": "Unauthorized"})
    try:
        if method == "GET" and parts == ["api", "accounts"]:
            return handle_list_accounts(user_info, config)
        if method == "GET" and parts == ["api", "config"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin"})
            return response(200, config)
        if method == "PUT" and parts == ["api", "config"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin"})
            migrate_json_to_db(json.loads(event.get("body", "{}") or "{}"))
            return response(200, {"message": "Config imported successfully"})
        if method == "POST" and parts == ["api", "accounts"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede crear cuentas"})
            return handle_create_account(json.loads(event.get("body", "{}") or "{}"))
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "accounts"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede eliminar cuentas"})
            return handle_delete_account(parts[2])
        if len(parts) >= 3 and parts[:2] == ["api", "accounts"]:
            account_id = parts[2]
            allowed_accounts = get_allowed_accounts(user_info, config)
            account = next((a for a in allowed_accounts if a["id"] == account_id), None)
            if not account:
                return response(403, {"error": "Access denied"})
            if len(parts) == 4 and parts[3] == "instances" and method == "GET":
                return handle_list_instances(account)
            if len(parts) == 4 and parts[3] == "instances" and method == "POST":
                if not is_superadmin(user_info):
                    return response(403, {"error": "Solo superadmin puede crear instancias"})
                return handle_create_instance(account_id, json.loads(event.get("body", "{}") or "{}"))
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
            if len(parts) >= 4 and parts[3] == "groups":
                if len(parts) == 4 and method == "POST":
                    if not is_superadmin(user_info):
                        return response(403, {"error": "Solo superadmin puede crear grupos"})
                    return handle_create_group(account_id, json.loads(event.get("body", "{}") or "{}"))
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
            if len(parts) == 4 and parts[3] == "schedule" and method == "GET":
                return handle_get_schedule(account, user_info)
            if len(parts) == 4 and parts[3] == "schedule" and method == "PUT":
                return handle_update_schedule(account, account_id, user_info, json.loads(event.get("body", "{}") or "{}"))
            if len(parts) == 4 and parts[3] == "notifications" and method == "GET":
                return handle_get_notifications(account, user_info)
            if len(parts) == 4 and parts[3] == "notifications" and method == "PUT":
                return handle_update_notifications(account, account_id, user_info, json.loads(event.get("body", "{}") or "{}"))
            if len(parts) == 5 and parts[3:5] == ["notifications", "test"] and method == "POST":
                return handle_test_notification(account, user_info, json.loads(event.get("body", "{}") or "{}"))
            if len(parts) == 4 and parts[3] == "costs" and method == "GET":
                return handle_get_costs(account, user_info)
            if len(parts) == 4 and parts[3] == "activity" and method == "GET":
                return handle_get_activity(account_id)
            if len(parts) == 4 and parts[3] == "activity" and method == "DELETE":
                if not is_admin(user_info):
                    return response(403, {"error": "Admin only"})
                return handle_clear_activity(account_id)
        if len(parts) >= 3 and parts[:2] == ["api", "keys"]:
            if method == "GET" and len(parts) == 3 and parts[2] == "list":
                if not is_admin(user_info):
                    return response(403, {"error": "Admin only"})
                return handle_list_keys(config)
            if method == "POST" and len(parts) == 3 and parts[2] == "create":
                if not is_admin(user_info):
                    return response(403, {"error": "Solo admin o superadmin puede crear API Keys"})
                body = json.loads(event.get("body", "{}") or "{}")
                return handle_create_key_validated(body, user_info)
            if method == "PUT" and len(parts) == 4 and parts[3] == "accounts":
                if not is_superadmin(user_info):
                    return response(403, {"error": "Solo superadmin"})
                return handle_update_key_accounts(parts[2], json.loads(event.get("body", "{}") or "{}"))
            if method == "DELETE" and len(parts) == 3:
                return handle_delete_key(parts[2], event)
        return response(404, {"error": "Not found"})
    except Exception as e:
        logger.error(f"[ERROR] {e!s}", exc_info=True)
        return response(500, {"error": str(e)})
