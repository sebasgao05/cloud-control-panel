"""
Cloud Control Panel - Scheduler handlers.
EventBridge Scheduler CRUD, activity logging, and scheduler event handling.
"""

import json
import os
from datetime import datetime, timezone

import boto3
from pydantic import ValidationError

from auth import get_scheduler_permissions
from notifications import send_notifications
from utils import REGION, db_delete, db_put, db_query, decimal_to_native, load_config_from_db, logger, response
from validators import UpdateScheduleRequest, format_validation_errors


def get_resource_tags():
    """Get standard tags from environment for dynamic resources."""
    return [
        {"Key": "Project", "Value": os.environ.get("PROJECT_TAG", "cloud-control-panel")},
        {"Key": "Environment", "Value": os.environ.get("ENVIRONMENT_TAG", "production")},
        {"Key": "Owner", "Value": os.environ.get("OWNER_TAG", "platform-team")},
        {"Key": "CostCenter", "Value": os.environ.get("COST_CENTER_TAG", "cloud-ops")},
        {"Key": "ManagedBy", "Value": "lambda-scheduler"},
        {"Key": "Component", "Value": "scheduler"},
    ]


def log_activity(account_id, action, user_name, instance_ids, rule_id=None, resource_type=None, resource_name=None):
    """Log an activity event to DynamoDB.

    Includes resource_type, resource_name, and ISO 8601 UTC timestamp.
    Implements retry-once logic: if the DynamoDB write fails, retries once.
    If still unsuccessful, logs to system error without blocking the caller.

    Args:
        account_id: The account identifier.
        action: The action performed (e.g. "start", "stop").
        user_name: The user or system that performed the action.
        instance_ids: List of resource IDs affected.
        rule_id: Optional scheduler rule ID that triggered the action.
        resource_type: Resource type (one of: ec2, rds, ecs, lightsail, apprunner).
        resource_name: Human-readable resource name.
    """
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    entry = {
        "action": action,
        "user": user_name,
        "resourceIds": instance_ids,
        "resourceType": resource_type,
        "resourceName": resource_name,
        "timestamp": ts,
        "ruleId": rule_id,
    }

    item = {"PK": f"ACTIVITY#{account_id}", "SK": ts, "data": entry}

    try:
        db_put(item)
    except Exception as e:
        logger.warning(f"[ACTIVITY LOG] First write attempt failed: {e}. Retrying...")
        try:
            db_put(item)
        except Exception as retry_err:
            logger.error(f"[ACTIVITY LOG] Retry failed, activity not recorded: {retry_err}")


def handle_get_activity(account_id):
    """Get activity log for an account (last 50 entries)."""
    items = db_query(f"ACTIVITY#{account_id}")
    items.sort(key=lambda x: x["SK"], reverse=True)
    entries = [decimal_to_native(i.get("data", {})) for i in items[:50]]
    return response(200, {"activities": entries})


def handle_clear_activity(account_id):
    """Clear all activity logs for an account."""
    items = db_query(f"ACTIVITY#{account_id}")
    for item in items:
        db_delete(item["PK"], item["SK"])
    return response(200, {"message": "Actividad eliminada"})


def handle_get_schedule(account, user_info):
    """Get schedule for an account."""
    permissions = get_scheduler_permissions(user_info)
    features = account.get("features", {})
    if not features.get("scheduler", False):
        return response(200, {"enabled": False, "permissions": {"view": False, "edit": False}, "schedule": None})
    if not permissions["view"]:
        return response(200, {"enabled": True, "permissions": {"view": False, "edit": False}, "schedule": None})
    schedule = account.get("schedule", {"timezone": "America/Bogota", "rules": []})
    instance_map = {inst["id"]: inst.get("name", inst["id"]) for inst in account.get("instances", [])}
    return response(
        200, {"enabled": True, "permissions": permissions, "schedule": schedule, "instanceMap": instance_map}
    )


def handle_update_schedule(account, account_id, user_info, body):
    """Update schedule rules for an account."""
    permissions = get_scheduler_permissions(user_info)
    if not permissions["edit"]:
        return response(200, {"error": "No tienes permiso", "denied": True})

    try:
        UpdateScheduleRequest.model_validate(body)
    except ValidationError as e:
        return response(400, {"error": "Validation error", "details": format_validation_errors(e)})

    existing = db_query(f"ACCOUNT#{account_id}", "SCHEDULE#")
    old_rule_ids = [item["SK"].replace("SCHEDULE#", "") for item in existing]
    for item in existing:
        db_delete(item["PK"], item["SK"])

    for old_id in old_rule_ids:
        delete_eventbridge_schedule(account_id, old_id, "start")
        delete_eventbridge_schedule(account_id, old_id, "stop")

    tz = body.get("timezone", account.get("schedule", {}).get("timezone", "America/Bogota"))
    for rule in body.get("rules", []):
        if not rule.get("id"):
            rule["id"] = f"rule-{int(datetime.now().timestamp())}"
        db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"SCHEDULE#{rule['id']}", "data": rule})
        if rule.get("enabled", True):
            create_eventbridge_schedule(account_id, account, rule, tz)

    send_notifications(account, "scheduler_executed", f"Programacion actualizada por {user_info.get('name', 'admin')}")
    return response(200, {"message": "Programacion actualizada y schedules creados en AWS"})


def handle_scheduler_event(event):
    """Handle scheduled start/stop invoked by EventBridge Scheduler.

    Supports two event formats:
    1. Legacy EC2-only: {"action", "accountId", "instanceIds", "ruleId"}
    2. Multi-service: {"action", "accountId", "resourceIds", "ruleId"}
       where resourceIds are config-level resource IDs (not AWS resource IDs).

    For multi-service events, dispatches to the appropriate adapter via get_adapter().
    For legacy events (instanceIds only), falls back to direct EC2 operations.
    """
    action = event.get("action")
    account_id = event.get("accountId")
    resource_ids = event.get("resourceIds", [])
    instance_ids = event.get("instanceIds", [])
    rule_id = event.get("ruleId", "unknown")

    # Validate: must have action, accountId, and at least one of resourceIds or instanceIds
    if not action or not account_id or (not resource_ids and not instance_ids):
        logger.error(f"[SCHEDULER EVENT] Invalid payload: {json.dumps(event)}")
        return {"statusCode": 400, "body": "Invalid scheduler event"}

    config = load_config_from_db()
    account = next((a for a in config.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        logger.error(f"[SCHEDULER EVENT] Account {account_id} not found")
        return {"statusCode": 404, "body": "Account not found"}

    # Multi-service path: dispatch via resource adapters
    if resource_ids:
        return _handle_scheduler_resource_event(account, account_id, action, resource_ids, rule_id)

    # Legacy EC2-only path (backward compatibility)
    return _handle_scheduler_ec2_event(account, account_id, action, instance_ids, rule_id)


def _handle_scheduler_resource_event(account, account_id, action, resource_ids, rule_id):
    """Handle scheduled event for multi-service resources via adapters.

    Looks up each resource by its config ID, determines its type, and invokes
    the appropriate adapter (EC2, RDS, ECS, Lightsail, or AppRunner).
    """
    from resource_adapter import get_adapter

    if action not in ("start", "stop"):
        return {"statusCode": 400, "body": f"Unknown action: {action}"}

    all_resources = account.get("resources", [])
    results = []
    errors = []

    for res_id in resource_ids:
        if not res_id:
            continue

        resource = next((r for r in all_resources if r.get("id") == res_id), None)
        if not resource:
            logger.warning(f"[SCHEDULER EVENT] Resource {res_id} not found in account {account_id}")
            errors.append(f"Resource {res_id} not found")
            continue

        resource_type = resource.get("type", "ec2")
        resource_name = resource.get("name", res_id)

        try:
            adapter = get_adapter(account, resource)
            if action == "start":
                adapter.start()
            else:
                adapter.stop()

            results.append(res_id)
            logger.info(
                f"[SCHEDULER EVENT] {action.upper()} resource={res_id} "
                f"type={resource_type} account={account_id} rule={rule_id}"
            )
            log_activity(
                account_id,
                action,
                "Scheduler",
                [res_id],
                rule_id=rule_id,
                resource_type=resource_type,
                resource_name=resource_name,
            )

        except Exception as e:
            logger.error(f"[SCHEDULER EVENT] Error {action} resource {res_id} (type={resource_type}): {e}")
            errors.append(f"{resource_type}:{res_id} - {e!s}")
            send_notifications(
                account,
                "error",
                f"Scheduler error ({action}) {resource_type} '{resource_name}': {e!s}",
            )

    # Send success notification for completed resources
    if results:
        action_label = "encendio" if action == "start" else "apago"
        msg = f"Scheduler {action_label}: {', '.join(results)}"
        scheduler_user = {"name": "Scheduler Automatico", "role": "scheduler"}
        send_notifications(account, "scheduler_executed", msg, scheduler_user)

    if errors and not results:
        return {"statusCode": 500, "body": f"All operations failed: {'; '.join(errors)}"}

    return {
        "statusCode": 200,
        "body": f"{action} executed for {len(results)} resources" + (f" ({len(errors)} errors)" if errors else ""),
    }


def _handle_scheduler_ec2_event(account, account_id, action, instance_ids, rule_id):
    """Handle scheduled event for EC2 instances (legacy path).

    Maintains backward compatibility with events that only contain instanceIds.
    """
    from ec2_ops import get_ec2_client

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
        log_activity(account_id, action, "Scheduler", valid_ids, rule_id, resource_type="ec2")
        scheduler_user = {"name": "Scheduler Automatico", "role": "scheduler"}
        send_notifications(account, "scheduler_executed", msg, scheduler_user)

    except Exception as e:
        logger.error(f"[SCHEDULER EVENT] Error: {e}")
        send_notifications(account, "error", f"Scheduler error ({action}): {e!s}")
        return {"statusCode": 500, "body": str(e)}

    return {"statusCode": 200, "body": f"{action} executed for {len(valid_ids)} instances"}


def cron_to_eventbridge(cron_expr, tz):
    """Convert '0 7 * * 1-5' to EventBridge format 'cron(0 7 ? * MON-FRI *)'."""
    parts = cron_expr.split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts

    day_map = {"0": "SUN", "1": "MON", "2": "TUE", "3": "WED", "4": "THU", "5": "FRI", "6": "SAT", "7": "SUN"}

    def convert_dow(d):
        if "-" in d:
            start, end = d.split("-")
            return f"{day_map.get(start, start)}-{day_map.get(end, end)}"
        if "," in d:
            return ",".join(day_map.get(x.strip(), x.strip()) for x in d.split(","))
        return day_map.get(d, d)

    eb_dow = convert_dow(dow)
    return f"cron({minute} {hour} ? {month} {eb_dow} *)"


def create_eventbridge_schedule(account_id, account, rule, tz):
    """Create start and stop EventBridge schedules for a rule.

    Supports both legacy EC2 instances and multi-service resources. If the rule
    contains 'resources' (resource config IDs), the event payload uses 'resourceIds'
    to trigger the multi-service adapter path. Otherwise falls back to 'instanceIds'
    for EC2-only backward compatibility.
    """
    scheduler = boto3.client("scheduler", region_name=REGION)
    lambda_arn = os.environ.get("LAMBDA_ARN", "")
    role_arn = os.environ.get("SCHEDULER_ROLE_ARN", "")
    stack_tag = os.environ.get("STACK_TAG", "ccp-main")

    if not lambda_arn or not role_arn:
        logger.warning("[SCHEDULER] Missing LAMBDA_ARN or SCHEDULER_ROLE_ARN")
        return

    rule_id = rule["id"]
    tags = get_resource_tags()

    # Determine if this rule targets multi-service resources or legacy EC2 instances
    resource_config_ids = rule.get("resources", [])
    instances = rule.get("instances", [])

    if resource_config_ids:
        # Multi-service path: pass resource config IDs directly
        event_payload_base = {
            "source": "scheduler",
            "accountId": account_id,
            "resourceIds": resource_config_ids,
            "ruleId": rule_id,
        }
    else:
        # Legacy EC2 path: resolve instance config IDs to EC2 instance IDs
        instance_ec2_ids = []
        for inst_config_id in instances:
            for inst in account.get("instances", []):
                if inst["id"] == inst_config_id:
                    instance_ec2_ids.append(inst.get("instanceId", ""))
                    break
        event_payload_base = {
            "source": "scheduler",
            "accountId": account_id,
            "instanceIds": instance_ec2_ids,
            "ruleId": rule_id,
        }

    tags = get_resource_tags()

    start_cron = cron_to_eventbridge(rule.get("startCron", ""), tz)
    if start_cron:
        start_payload = {**event_payload_base, "action": "start"}
        schedule_params = {
            "Name": f"{stack_tag}-{account_id}-{rule_id}-start",
            "GroupName": "default",
            "ScheduleExpression": start_cron,
            "ScheduleExpressionTimezone": tz,
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": lambda_arn,
                "RoleArn": role_arn,
                "Input": json.dumps(start_payload),
            },
            "State": "ENABLED",
        }
        try:
            scheduler.create_schedule(**schedule_params, Tags=tags)
            logger.info(f"[SCHEDULER] Created start schedule for {rule_id}")
        except scheduler.exceptions.ConflictException:
            scheduler.update_schedule(**schedule_params)

    stop_cron = cron_to_eventbridge(rule.get("stopCron", ""), tz)
    if stop_cron:
        stop_payload = {**event_payload_base, "action": "stop"}
        schedule_params = {
            "Name": f"{stack_tag}-{account_id}-{rule_id}-stop",
            "GroupName": "default",
            "ScheduleExpression": stop_cron,
            "ScheduleExpressionTimezone": tz,
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": lambda_arn,
                "RoleArn": role_arn,
                "Input": json.dumps(stop_payload),
            },
            "State": "ENABLED",
        }
        try:
            scheduler.create_schedule(**schedule_params, Tags=tags)
            logger.info(f"[SCHEDULER] Created stop schedule for {rule_id}")
        except scheduler.exceptions.ConflictException:
            scheduler.update_schedule(**schedule_params)


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
