"""
Cloud Control Panel - Scheduler handlers.
EventBridge Scheduler CRUD, activity logging, and scheduler event handling.
"""

import json
import os
from datetime import datetime, timezone

import boto3

from auth import get_scheduler_permissions
from notifications import send_notifications
from utils import REGION, db_delete, db_put, db_query, decimal_to_native, load_config_from_db, logger, response


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
    return response(200, {"enabled": True, "permissions": permissions, "schedule": schedule, "instanceMap": instance_map})


def handle_update_schedule(account, account_id, user_info, body):
    """Update schedule rules for an account."""
    permissions = get_scheduler_permissions(user_info)
    if not permissions["edit"]:
        return response(200, {"error": "No tienes permiso", "denied": True})

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
    """Handle scheduled start/stop invoked by EventBridge Scheduler."""
    action = event.get("action")
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
        log_activity(account_id, action, "Scheduler", valid_ids, rule_id)
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

    instance_ec2_ids = []
    for inst_config_id in instances:
        for inst in account.get("instances", []):
            if inst["id"] == inst_config_id:
                instance_ec2_ids.append(inst.get("instanceId", ""))
                break

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
                    "Arn": lambda_arn, "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler", "action": "start",
                        "accountId": account_id, "instanceIds": instance_ec2_ids, "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )
            logger.info(f"[SCHEDULER] Created start schedule for {rule_id}")
        except scheduler.exceptions.ConflictException:
            scheduler.update_schedule(
                Name=f"{stack_tag}-{account_id}-{rule_id}-start",
                GroupName="default",
                ScheduleExpression=start_cron,
                ScheduleExpressionTimezone=tz,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn, "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler", "action": "start",
                        "accountId": account_id, "instanceIds": instance_ec2_ids, "ruleId": rule_id,
                    }),
                },
                State="ENABLED",
            )

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
                    "Arn": lambda_arn, "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler", "action": "stop",
                        "accountId": account_id, "instanceIds": instance_ec2_ids, "ruleId": rule_id,
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
                    "Arn": lambda_arn, "RoleArn": role_arn,
                    "Input": json.dumps({
                        "source": "scheduler", "action": "stop",
                        "accountId": account_id, "instanceIds": instance_ec2_ids, "ruleId": rule_id,
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
