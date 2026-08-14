"""
Cloud Control Panel - EC2/SSM operations, instance and group handlers.
"""

from datetime import datetime, timezone

import boto3

from auth import find_instance
from utils import REGION, logger, response


def get_ec2_client(account):
    """Get EC2 client, with optional cross-account role assumption."""
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)
    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="CloudControlPanel")["Credentials"]
        return boto3.client(
            "ec2",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("ec2", region_name=region)


def get_ssm_client(account):
    """Get SSM client, with optional cross-account role assumption."""
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)
    if role_arn:
        sts = boto3.client("sts", region_name=region)
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="CloudControlPanel")["Credentials"]
        return boto3.client(
            "ssm",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("ssm", region_name=region)


def handle_list_accounts(user_info, config):
    """List accounts accessible to the user."""
    from auth import get_allowed_accounts

    accounts = get_allowed_accounts(user_info, config)
    result = [
        {
            "id": a["id"],
            "name": a.get("name", a["id"]),
            "awsAccountId": a.get("awsAccountId", ""),
            "region": a.get("region", REGION),
            "instanceCount": len(a.get("instances", [])),
            "groupCount": len(a.get("groups", [])),
        }
        for a in accounts
    ]
    return response(
        200, {"accounts": result, "user": user_info.get("name", ""), "role": user_info.get("role", "operator")}
    )


def handle_list_instances(account):
    """List instances for an account with live EC2 state."""
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
        result_instances.append(
            {
                "id": inst["id"],
                "name": inst.get("name", inst["id"]),
                "instanceId": inst.get("instanceId", ""),
                "description": inst.get("description", ""),
                "dashboardPort": inst.get("dashboardPort"),
                "group": inst.get("group"),
                "state": state,
                "publicIp": live.get("publicIp"),
                "uptime": uptime,
            }
        )

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
        result_groups.append(
            {
                "id": grp["id"],
                "name": grp.get("name", grp["id"]),
                "description": grp.get("description", ""),
                "color": grp.get("color", "#6366f1"),
                "members": member_ids,
                "state": group_state,
            }
        )

    return response(
        200,
        {
            "accountId": account["id"],
            "accountName": account.get("name", ""),
            "instances": result_instances,
            "groups": result_groups,
        },
    )


def handle_instance_status(account, instance):
    """Get live status of a single instance."""
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
    return response(
        200,
        {
            "id": instance["id"],
            "name": instance.get("name", ""),
            "instanceId": instance["instanceId"],
            "state": state,
            "publicIp": inst_data.get("PublicIpAddress"),
            "uptime": uptime,
            "dashboardPort": instance.get("dashboardPort"),
            "description": instance.get("description", ""),
            "group": instance.get("group"),
        },
    )


def handle_instance_start(account, instance, user_info):
    """Start an EC2 instance."""
    from notifications import send_notifications
    from scheduler import log_activity

    ec2 = get_ec2_client(account)
    ec2.start_instances(InstanceIds=[instance["instanceId"]])
    logger.info(f"[ACTION] user={user_info['name']} action=START instance={instance['instanceId']}")
    log_activity(
        account["id"],
        "start",
        user_info.get("name", "unknown"),
        [instance["instanceId"]],
        resource_type="ec2",
        resource_name=instance.get("name", instance["id"]),
    )
    send_notifications(account, "started", instance.get("name", instance["id"]), user_info)
    return response(200, {"message": "Instance starting", "instanceId": instance["instanceId"]})


def handle_instance_stop(account, instance, user_info):
    """Stop an EC2 instance."""
    from notifications import send_notifications
    from scheduler import log_activity

    ec2 = get_ec2_client(account)
    ec2.stop_instances(InstanceIds=[instance["instanceId"]])
    logger.info(f"[ACTION] user={user_info['name']} action=STOP instance={instance['instanceId']}")
    log_activity(
        account["id"],
        "stop",
        user_info.get("name", "unknown"),
        [instance["instanceId"]],
        resource_type="ec2",
        resource_name=instance.get("name", instance["id"]),
    )
    send_notifications(account, "stopped", instance.get("name", instance["id"]), user_info)
    return response(200, {"message": "Instance stopping", "instanceId": instance["instanceId"]})


def handle_instance_update(account, instance, user_info):
    """Run update command on an instance via SSM."""
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
    return response(200, {"message": "Update started", "commandId": cmd["Command"]["CommandId"]})


def handle_dashboard_url(account, instance):
    """Get the dashboard URL for an instance."""
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
    """Get status of all instances in a group."""
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
            members.append(
                {
                    "id": ci.get("id"),
                    "name": ci.get("name"),
                    "instanceId": d["InstanceId"],
                    "state": d["State"]["Name"],
                    "publicIp": d.get("PublicIpAddress"),
                }
            )
    states = [m["state"] for m in members]
    gs = (
        "running"
        if all(s == "running" for s in states)
        else "stopped"
        if all(s == "stopped" for s in states)
        else "partial"
    )
    return response(200, {"group": group["id"], "name": group.get("name"), "state": gs, "members": members})


def handle_group_start(account, group, user_info):
    """Start all instances in a group."""
    from notifications import send_notifications

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
    """Stop all instances in a group."""
    from notifications import send_notifications

    ec2 = get_ec2_client(account)
    stopped = []
    for mid in group.get("stopOrder", []):
        inst = find_instance(account, mid)
        if inst:
            ec2.stop_instances(InstanceIds=[inst["instanceId"]])
            stopped.append({"id": inst["id"], "name": inst.get("name")})
    send_notifications(account, "stopped", f"Grupo {group.get('name')}", user_info)
    return response(200, {"message": "Group stopping", "group": group["id"], "stopped": stopped})
