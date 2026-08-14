"""Cloud Control Panel - Lambda handler (router). Entry point: app.lambda_handler."""

import json
import os

from pydantic import ValidationError

from admin import (
    handle_create_account,
    handle_create_group,
    handle_create_instance,
    handle_create_key_validated,
    handle_delete_account,
    handle_delete_group,
    handle_delete_instance,
    handle_delete_key,
    handle_get_costs,
    handle_list_keys,
    handle_update_key_accounts,
)
from auth import authenticate, find_group, find_instance, find_resource, get_allowed_accounts, is_admin, is_superadmin
from ec2_ops import (
    handle_dashboard_url,
    handle_group_start,
    handle_group_status,
    handle_group_stop,
    handle_instance_start,
    handle_instance_status,
    handle_instance_stop,
    handle_instance_update,
    handle_list_accounts,
    handle_list_instances,
)
from notifications import handle_get_notifications, handle_test_notification, handle_update_notifications
from scheduler import (
    handle_clear_activity,
    handle_get_activity,
    handle_get_schedule,
    handle_scheduler_event,
    handle_update_schedule,
)
from utils import (
    CONFIG_PATH,
    db_delete,
    db_put,
    is_db_initialized,
    load_config_from_db,
    logger,
    migrate_json_to_db,
    migrate_plaintext_keys_to_bcrypt,
    response,
)
from validators import ImportConfigRequest, format_validation_errors, validate_path_parameter
from validators import CreateResourceRequest, check_duplicate_resource_id
from resource_adapter import get_adapter
from uptime import get_uptime_data
from metrics import handle_get_metrics


def _handle_resource_action(account: dict, resource: dict, action: str) -> dict:
    """Handle resource start/stop/status via the adapter factory.

    Routes to the correct service adapter based on resource type and executes
    the requested action. Handles all adapter errors with appropriate HTTP codes.

    Args:
        account: Account configuration dict.
        resource: Resource configuration dict with a 'type' field.
        action: One of "start", "stop", or "status".

    Returns:
        API Gateway response dict.
    """
    try:
        adapter = get_adapter(account, resource)
    except ValueError as e:
        return response(400, {"error": str(e)})

    try:
        if action == "status":
            result = adapter.status()
        elif action == "start":
            result = adapter.start()
        elif action == "stop":
            result = adapter.stop()
        else:
            return response(400, {"error": f"Unknown action: {action}"})
        return response(200, result)
    except PermissionError as e:
        return response(403, {"error": str(e)})
    except RuntimeError as e:
        return response(401, {"error": str(e)})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        logger.error(f"[RESOURCE] Action '{action}' failed for resource {resource.get('id')}: {e!s}", exc_info=True)
        return response(500, {"error": f"Resource operation failed: {type(e).__name__}"})


def _handle_resource_metrics(account: dict, resource: dict) -> dict:
    """Handle GET /api/accounts/{id}/resources/{rid}/metrics.

    Fetches the resource's current state via its adapter, then queries
    CloudWatch for CPU and memory metrics. Returns empty metrics if the
    resource is not running, and a 503 on timeout/failure.

    Args:
        account: Account configuration dict.
        resource: Resource configuration dict.

    Returns:
        API Gateway response dict.
    """
    # Get the current resource state from the adapter
    try:
        adapter = get_adapter(account, resource)
        status_result = adapter.status()
        resource_with_state = {**resource, "state": status_result.get("state", "unknown")}
    except Exception as e:
        logger.error(f"[METRICS] Failed to get resource state for {resource.get('id')}: {e!s}")
        return response(503, {"error": "Metrics temporarily unavailable"})

    result = handle_get_metrics(account, resource_with_state)

    # If metrics handler returned an error, respond with 503
    if "error" in result:
        return response(503, {"error": result["error"]})

    return response(200, result)

def lambda_handler(event, context):
    """Main Lambda entry point - routes requests to handler modules."""
    if event.get("source") == "scheduler":
        return handle_scheduler_event(event)
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    raw_path = event.get("rawPath", "/")
    stage = event.get("requestContext", {}).get("stage", "")
    if stage and stage != "$default" and raw_path.startswith(f"/{stage}"):
        path = raw_path[len(f"/{stage}") :]
    else:
        path = raw_path
    if not path:
        path = "/"
    if not is_db_initialized():
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                migrate_json_to_db(json.load(f))
            logger.info("[INIT] Auto-migrated JSON config to DynamoDB")

    # Run bcrypt key migration if not already done
    migrate_plaintext_keys_to_bcrypt()

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
            body = json.loads(event.get("body", "{}") or "{}")
            try:
                ImportConfigRequest.model_validate(body)
            except ValidationError as e:
                return response(400, {"error": "Validation error", "details": format_validation_errors(e)})
            migrate_json_to_db(body)
            return response(200, {"message": "Config imported successfully"})
        if method == "POST" and parts == ["api", "accounts"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede crear cuentas"})
            return handle_create_account(json.loads(event.get("body", "{}") or "{}"))
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "accounts"]:
            if not is_superadmin(user_info):
                return response(403, {"error": "Solo superadmin puede eliminar cuentas"})
            if not validate_path_parameter(parts[2]):
                return response(400, {"error": "Invalid account_id format"})
            return handle_delete_account(parts[2])
        if len(parts) >= 3 and parts[:2] == ["api", "accounts"]:
            account_id = parts[2]
            if not validate_path_parameter(account_id):
                return response(400, {"error": "Invalid account_id format"})
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
                if not validate_path_parameter(parts[4]):
                    return response(400, {"error": "Invalid instance_id format"})
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
            # --- Multi-service resource routes ---
            if len(parts) == 4 and parts[3] == "resources" and method == "GET":
                resources = account.get("resources", [])
                return response(200, {"resources": resources})
            if len(parts) == 4 and parts[3] == "resources" and method == "POST":
                if not is_superadmin(user_info):
                    return response(403, {"error": "Solo superadmin puede crear recursos"})
                body = json.loads(event.get("body", "{}") or "{}")
                try:
                    validated = CreateResourceRequest.model_validate(body)
                except ValidationError as e:
                    return response(400, {"error": "Validation error", "details": format_validation_errors(e)})
                existing_resources = account.get("resources", [])
                if check_duplicate_resource_id(existing_resources, validated.id):
                    return response(400, {"error": f"Resource with id '{validated.id}' already exists in this account"})
                resource_data = body.copy()
                db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"RESOURCE#{validated.id}", "data": resource_data})
                return response(200, {"message": f"Resource {validated.id} created", "id": validated.id})
            if len(parts) >= 5 and parts[3] == "resources":
                resource_id = parts[4]
                if not validate_path_parameter(resource_id):
                    return response(400, {"error": "Invalid resource_id format"})
                resource = find_resource(account, resource_id)
                if not resource:
                    return response(404, {"error": "Resource not found"})
                if len(parts) == 5 and method == "DELETE":
                    if not is_superadmin(user_info):
                        return response(403, {"error": "Solo superadmin puede eliminar recursos"})
                    db_delete(f"ACCOUNT#{account_id}", f"RESOURCE#{resource_id}")
                    return response(200, {"message": f"Resource {resource_id} deleted"})
                if len(parts) == 6:
                    action = parts[5]
                    if method == "GET" and action == "status":
                        return _handle_resource_action(account, resource, "status")
                    if method == "POST" and action == "start":
                        return _handle_resource_action(account, resource, "start")
                    if method == "POST" and action == "stop":
                        return _handle_resource_action(account, resource, "stop")
                    if method == "GET" and action == "uptime":
                        # GET /api/accounts/{id}/resources/{rid}/uptime?range=7|30
                        qs = event.get("queryStringParameters") or {}
                        range_param = qs.get("range", "7")
                        days = 30 if range_param == "30" else 7
                        result = get_uptime_data(account_id, resource_id, days)
                        return response(200, result)
                    if method == "GET" and action == "metrics":
                        return _handle_resource_metrics(account, resource)
            if len(parts) >= 4 and parts[3] == "groups":
                if len(parts) == 4 and method == "POST":
                    if not is_superadmin(user_info):
                        return response(403, {"error": "Solo superadmin puede crear grupos"})
                    return handle_create_group(account_id, json.loads(event.get("body", "{}") or "{}"))
                if len(parts) >= 5:
                    if not validate_path_parameter(parts[4]):
                        return response(400, {"error": "Invalid group_id format"})
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
                return handle_update_schedule(
                    account, account_id, user_info, json.loads(event.get("body", "{}") or "{}")
                )
            if len(parts) == 4 and parts[3] == "notifications" and method == "GET":
                return handle_get_notifications(account, user_info)
            if len(parts) == 4 and parts[3] == "notifications" and method == "PUT":
                return handle_update_notifications(
                    account, account_id, user_info, json.loads(event.get("body", "{}") or "{}")
                )
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
                if not validate_path_parameter(parts[2]):
                    return response(400, {"error": "Invalid key_id format"})
                return handle_update_key_accounts(parts[2], json.loads(event.get("body", "{}") or "{}"))
            if method == "PUT" and len(parts) == 3:
                if not is_admin(user_info):
                    return response(403, {"error": "Solo admin o superadmin"})
                if not validate_path_parameter(parts[2]):
                    return response(400, {"error": "Invalid key_id format"})
                from admin import handle_update_key

                return handle_update_key(parts[2], json.loads(event.get("body", "{}") or "{}"), user_info)
            if method == "DELETE" and len(parts) == 3:
                if not validate_path_parameter(parts[2]):
                    return response(400, {"error": "Invalid key_id format"})
                return handle_delete_key(parts[2], event)
        return response(404, {"error": "Not found"})
    except Exception as e:
        logger.error(f"[ERROR] {e!s}", exc_info=True)
        return response(500, {"error": "Internal server error"})
