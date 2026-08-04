"""
Cloud Control Panel - Lambda handler (Multi-account, Multi-instance)
Handles all API routes for managing EC2 instances across multiple AWS accounts.
"""

import json
import os
import boto3
from datetime import datetime, timezone

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def load_config():
    """Load accounts configuration from bundled JSON file."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_ec2_client(account):
    """Get EC2 client, assuming cross-account role if needed."""
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)

    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudControlPanel"
        )["Credentials"]
        return boto3.client(
            "ec2",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("ec2", region_name=region)


def get_ssm_client(account):
    """Get SSM client, assuming cross-account role if needed."""
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)

    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudControlPanel"
        )["Credentials"]
        return boto3.client(
            "ssm",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("ssm", region_name=region)


def authenticate(event, config):
    """Validate API key and return user info with allowed accounts."""
    headers = event.get("headers", {})
    provided_key = headers.get("x-api-key", "")

    api_keys = config.get("apiKeys", {})
    user_info = api_keys.get(provided_key)

    if not user_info:
        return None

    return user_info


def get_allowed_accounts(user_info, config):
    """Filter accounts based on user permissions."""
    all_accounts = config.get("accounts", [])
    allowed = user_info.get("accounts", [])

    if "*" in allowed:
        return all_accounts

    return [acc for acc in all_accounts if acc["id"] in allowed]


def find_account(config, account_id):
    """Find account by ID in config."""
    for acc in config.get("accounts", []):
        if acc["id"] == account_id:
            return acc
    return None


def find_instance(account, instance_id):
    """Find instance by ID within an account."""
    for inst in account.get("instances", []):
        if inst["id"] == instance_id:
            return inst
    return None


def find_group(account, group_id):
    """Find group by ID within an account."""
    for grp in account.get("groups", []):
        if grp["id"] == group_id:
            return grp
    return None


def lambda_handler(event, context):
    """Main router for API Gateway HTTP API."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    raw_path = event.get("rawPath", "/")
    stage = event.get("requestContext", {}).get("stage", "")
    if stage and stage != "$default" and raw_path.startswith(f"/{stage}"):
        path = raw_path[len(f"/{stage}"):]
    else:
        path = raw_path
    if not path:
        path = "/"

    # Load config
    config = load_config()

    # Authenticate
    user_info = authenticate(event, config)
    if not user_info:
        return response(401, {"error": "Unauthorized"})

    # Route matching
    # GET  /api/accounts
    # GET  /api/accounts/{accountId}/instances
    # GET  /api/accounts/{accountId}/instances/{instanceId}/status
    # POST /api/accounts/{accountId}/instances/{instanceId}/start
    # POST /api/accounts/{accountId}/instances/{instanceId}/stop
    # POST /api/accounts/{accountId}/instances/{instanceId}/update
    # GET  /api/accounts/{accountId}/instances/{instanceId}/dashboard-url
    # POST /api/accounts/{accountId}/groups/{groupId}/start
    # POST /api/accounts/{accountId}/groups/{groupId}/stop
    # GET  /api/accounts/{accountId}/groups/{groupId}/status

    parts = path.strip("/").split("/")

    try:
        # GET /api/accounts
        if method == "GET" and parts == ["api", "accounts"]:
            return handle_list_accounts(user_info, config)

        # /api/accounts/{accountId}/...
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "accounts":
            account_id = parts[2]

            # Check access
            allowed_accounts = get_allowed_accounts(user_info, config)
            account = None
            for acc in allowed_accounts:
                if acc["id"] == account_id:
                    account = acc
                    break
            if not account:
                return response(403, {"error": "Access denied to this account"})

            # GET /api/accounts/{accountId}/instances
            if len(parts) == 4 and parts[3] == "instances" and method == "GET":
                return handle_list_instances(account)

            # /api/accounts/{accountId}/instances/{instanceId}/...
            if len(parts) >= 5 and parts[3] == "instances":
                instance_id = parts[4]
                instance = find_instance(account, instance_id)
                if not instance:
                    return response(404, {"error": "Instance not found"})

                if len(parts) == 6:
                    action = parts[5]
                    if method == "GET" and action == "status":
                        return handle_instance_status(account, instance)
                    if method == "POST" and action == "start":
                        return handle_instance_start(account, instance)
                    if method == "POST" and action == "stop":
                        return handle_instance_stop(account, instance)
                    if method == "POST" and action == "update":
                        return handle_instance_update(account, instance)
                    if method == "GET" and action == "dashboard-url":
                        return handle_dashboard_url(account, instance)

            # /api/accounts/{accountId}/groups/{groupId}/...
            if len(parts) >= 5 and parts[3] == "groups":
                group_id = parts[4]
                group = find_group(account, group_id)
                if not group:
                    return response(404, {"error": "Group not found"})

                if len(parts) == 6:
                    action = parts[5]
                    if method == "GET" and action == "status":
                        return handle_group_status(account, group)
                    if method == "POST" and action == "start":
                        return handle_group_start(account, group)
                    if method == "POST" and action == "stop":
                        return handle_group_stop(account, group)

        return response(404, {"error": "Not found"})

    except Exception as e:
        return response(500, {"error": str(e)})


# ─── Handlers ───────────────────────────────────────────────────────────

def handle_list_accounts(user_info, config):
    """List accounts the user has access to."""
    accounts = get_allowed_accounts(user_info, config)
    result = []
    for acc in accounts:
        result.append({
            "id": acc["id"],
            "name": acc["name"],
            "awsAccountId": acc["awsAccountId"],
            "region": acc.get("region", REGION),
            "instanceCount": len(acc.get("instances", [])),
            "groupCount": len(acc.get("groups", [])),
        })
    return response(200, {"accounts": result, "user": user_info.get("name", "")})


def handle_list_instances(account):
    """List all instances and groups in an account with live status."""
    ec2 = get_ec2_client(account)

    instances = account.get("instances", [])
    instance_ids = [inst["instanceId"] for inst in instances]

    # Fetch live status for all instances in one call
    states = {}
    if instance_ids:
        desc = ec2.describe_instances(InstanceIds=instance_ids)
        for res in desc.get("Reservations", []):
            for inst in res.get("Instances", []):
                iid = inst["InstanceId"]
                states[iid] = {
                    "state": inst["State"]["Name"],
                    "publicIp": inst.get("PublicIpAddress"),
                    "launchTime": inst.get("LaunchTime"),
                }

    # Build response
    result_instances = []
    for inst in instances:
        live = states.get(inst["instanceId"], {})
        state = live.get("state", "unknown")
        launch_time = live.get("launchTime")

        uptime = None
        if state == "running" and launch_time:
            delta = datetime.now(timezone.utc) - launch_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes = remainder // 60
            uptime = f"{hours}h {minutes}m"

        result_instances.append({
            "id": inst["id"],
            "name": inst["name"],
            "instanceId": inst["instanceId"],
            "description": inst.get("description", ""),
            "dashboardPort": inst.get("dashboardPort"),
            "group": inst.get("group"),
            "state": state,
            "publicIp": live.get("publicIp"),
            "uptime": uptime,
        })

    groups = account.get("groups", [])
    result_groups = []
    for grp in groups:
        # Determine group state based on member instances
        member_ids = grp.get("startOrder", [])
        member_states = []
        for mid in member_ids:
            for ri in result_instances:
                if ri["id"] == mid:
                    member_states.append(ri["state"])
                    break

        if all(s == "running" for s in member_states):
            group_state = "running"
        elif all(s == "stopped" for s in member_states):
            group_state = "stopped"
        else:
            group_state = "partial"

        result_groups.append({
            "id": grp["id"],
            "name": grp["name"],
            "description": grp.get("description", ""),
            "members": member_ids,
            "state": group_state,
        })

    return response(200, {
        "accountId": account["id"],
        "accountName": account["name"],
        "instances": result_instances,
        "groups": result_groups,
    })


def handle_instance_status(account, instance):
    """Get detailed status for a single instance."""
    ec2 = get_ec2_client(account)

    desc = ec2.describe_instances(InstanceIds=[instance["instanceId"]])
    inst_data = desc["Reservations"][0]["Instances"][0]

    state = inst_data["State"]["Name"]
    public_ip = inst_data.get("PublicIpAddress")
    launch_time = inst_data.get("LaunchTime")

    uptime = None
    if state == "running" and launch_time:
        delta = datetime.now(timezone.utc) - launch_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        uptime = f"{hours}h {minutes}m"

    return response(200, {
        "id": instance["id"],
        "name": instance["name"],
        "instanceId": instance["instanceId"],
        "state": state,
        "publicIp": public_ip,
        "uptime": uptime,
        "dashboardPort": instance.get("dashboardPort"),
        "description": instance.get("description", ""),
        "group": instance.get("group"),
    })


def handle_instance_start(account, instance):
    """Start a single instance."""
    ec2 = get_ec2_client(account)
    ec2.start_instances(InstanceIds=[instance["instanceId"]])
    return response(200, {
        "message": "Instance starting",
        "instanceId": instance["instanceId"],
        "name": instance["name"],
    })


def handle_instance_stop(account, instance):
    """Stop a single instance."""
    ec2 = get_ec2_client(account)
    ec2.stop_instances(InstanceIds=[instance["instanceId"]])
    return response(200, {
        "message": "Instance stopping",
        "instanceId": instance["instanceId"],
        "name": instance["name"],
    })


def handle_instance_update(account, instance):
    """Trigger update via SSM Run Command."""
    ssm = get_ssm_client(account)
    cmd = ssm.send_command(
        InstanceIds=[instance["instanceId"]],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [
                'sudo -u ec2-user bash -lc "cd ~/app && git pull && bash install.sh"',
                "sudo systemctl restart app",
            ],
            "executionTimeout": ["600"],
        },
    )
    command_id = cmd["Command"]["CommandId"]
    return response(200, {
        "message": "Update started",
        "commandId": command_id,
        "instanceId": instance["instanceId"],
    })


def handle_dashboard_url(account, instance):
    """Get dashboard URL for an instance."""
    port = instance.get("dashboardPort")
    if not port:
        return response(200, {"url": None, "reason": "No dashboard configured"})

    ec2 = get_ec2_client(account)
    desc = ec2.describe_instances(InstanceIds=[instance["instanceId"]])
    inst_data = desc["Reservations"][0]["Instances"][0]
    public_ip = inst_data.get("PublicIpAddress")

    if not public_ip:
        return response(200, {"url": None, "reason": "Instance is not running"})

    url = f"http://{public_ip}:{port}"
    return response(200, {"url": url})


def handle_group_status(account, group):
    """Get status of all instances in a group."""
    ec2 = get_ec2_client(account)
    member_ids = group.get("startOrder", [])

    # Get instance IDs from config
    instance_ids = []
    instances_map = {}
    for mid in member_ids:
        inst = find_instance(account, mid)
        if inst:
            instance_ids.append(inst["instanceId"])
            instances_map[inst["instanceId"]] = inst

    if not instance_ids:
        return response(200, {"group": group["id"], "members": [], "state": "empty"})

    desc = ec2.describe_instances(InstanceIds=instance_ids)
    members = []
    for res in desc.get("Reservations", []):
        for inst_data in res.get("Instances", []):
            iid = inst_data["InstanceId"]
            config_inst = instances_map.get(iid, {})
            members.append({
                "id": config_inst.get("id", iid),
                "name": config_inst.get("name", iid),
                "instanceId": iid,
                "state": inst_data["State"]["Name"],
                "publicIp": inst_data.get("PublicIpAddress"),
            })

    states = [m["state"] for m in members]
    if all(s == "running" for s in states):
        group_state = "running"
    elif all(s == "stopped" for s in states):
        group_state = "stopped"
    else:
        group_state = "partial"

    return response(200, {
        "group": group["id"],
        "name": group["name"],
        "state": group_state,
        "members": members,
    })


def handle_group_start(account, group):
    """Start all instances in a group respecting startOrder."""
    ec2 = get_ec2_client(account)
    start_order = group.get("startOrder", [])

    started = []
    for member_id in start_order:
        inst = find_instance(account, member_id)
        if inst:
            ec2.start_instances(InstanceIds=[inst["instanceId"]])
            started.append({"id": inst["id"], "name": inst["name"], "instanceId": inst["instanceId"]})

    return response(200, {
        "message": "Group starting",
        "group": group["id"],
        "started": started,
    })


def handle_group_stop(account, group):
    """Stop all instances in a group respecting stopOrder."""
    ec2 = get_ec2_client(account)
    stop_order = group.get("stopOrder", [])

    stopped = []
    for member_id in stop_order:
        inst = find_instance(account, member_id)
        if inst:
            ec2.stop_instances(InstanceIds=[inst["instanceId"]])
            stopped.append({"id": inst["id"], "name": inst["name"], "instanceId": inst["instanceId"]})

    return response(200, {
        "message": "Group stopping",
        "group": group["id"],
        "stopped": stopped,
    })


# ─── Response helper ────────────────────────────────────────────────────

def response(status_code, body):
    """Build API Gateway HTTP API response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
        },
        "body": json.dumps(body, default=str),
    }
