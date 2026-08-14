"""
Cloud Control Panel - CloudWatch Metrics endpoint.

Fetches CPU and memory utilization metrics for running resources.
Uses cross-account STS sessions for remote accounts.
"""

from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from utils import REGION, logger


# 10-second timeout for CloudWatch API calls
_CW_TIMEOUT_CONFIG = Config(
    connect_timeout=5,
    read_timeout=10,
    retries={"max_attempts": 1},
)


def _get_cloudwatch_client(account: dict):
    """Create a CloudWatch client with cross-account support if needed.

    Uses STS AssumeRole for accounts with crossAccountRoleArn configured.
    Falls back to Lambda execution role credentials otherwise.
    """
    role_arn = account.get("crossAccountRoleArn")
    region = account.get("region", REGION)

    if not role_arn:
        return boto3.client("cloudwatch", region_name=region, config=_CW_TIMEOUT_CONFIG)

    sts = boto3.client("sts", region_name=region)
    creds = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="CloudControlPanel",
        DurationSeconds=3600,
    )["Credentials"]

    return boto3.client(
        "cloudwatch",
        region_name=region,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        config=_CW_TIMEOUT_CONFIG,
    )


def _get_metric_dimensions(resource: dict) -> dict:
    """Return CloudWatch namespace and dimensions based on resource type.

    Returns:
        dict with keys: cpu_namespace, cpu_dimensions, cpu_metric_name,
                        memory_namespace, memory_dimensions, memory_metric_name
        or None if the resource type is not supported for metrics.
    """
    resource_type = resource.get("type", "ec2")
    resource_id = resource.get("resourceId", "")

    if resource_type == "ec2":
        return {
            "cpu_namespace": "AWS/EC2",
            "cpu_metric_name": "CPUUtilization",
            "cpu_dimensions": [{"Name": "InstanceId", "Value": resource_id}],
            "memory_namespace": "CWAgent",
            "memory_metric_name": "mem_used_percent",
            "memory_dimensions": [{"Name": "InstanceId", "Value": resource_id}],
            "supports_memory": True,
        }
    elif resource_type == "ecs":
        # ECS resourceId format: "cluster-name/service-name"
        parts = resource_id.split("/")
        cluster_name = parts[0] if len(parts) >= 2 else resource_id
        service_name = parts[1] if len(parts) >= 2 else resource_id

        return {
            "cpu_namespace": "AWS/ECS",
            "cpu_metric_name": "CPUUtilization",
            "cpu_dimensions": [
                {"Name": "ClusterName", "Value": cluster_name},
                {"Name": "ServiceName", "Value": service_name},
            ],
            "memory_namespace": "AWS/ECS",
            "memory_metric_name": "MemoryUtilization",
            "memory_dimensions": [
                {"Name": "ClusterName", "Value": cluster_name},
                {"Name": "ServiceName", "Value": service_name},
            ],
            "supports_memory": True,
        }
    elif resource_type == "rds":
        return {
            "cpu_namespace": "AWS/RDS",
            "cpu_metric_name": "CPUUtilization",
            "cpu_dimensions": [{"Name": "DBInstanceIdentifier", "Value": resource_id}],
            "memory_namespace": None,
            "memory_metric_name": None,
            "memory_dimensions": None,
            "supports_memory": False,
        }
    elif resource_type == "lightsail":
        return {
            "cpu_namespace": "AWS/Lightsail",
            "cpu_metric_name": "CPUUtilization",
            "cpu_dimensions": [{"Name": "InstanceName", "Value": resource_id}],
            "memory_namespace": None,
            "memory_metric_name": None,
            "memory_dimensions": None,
            "supports_memory": False,
        }
    elif resource_type == "apprunner":
        return {
            "cpu_namespace": "AWS/AppRunner",
            "cpu_metric_name": "CPUUtilization",
            "cpu_dimensions": [{"Name": "ServiceArn", "Value": resource_id}],
            "memory_namespace": None,
            "memory_metric_name": None,
            "memory_dimensions": None,
            "supports_memory": False,
        }
    else:
        return None


def _query_metric(client, namespace: str, metric_name: str, dimensions: list, start_time, end_time) -> list:
    """Query CloudWatch for a single metric and return sorted datapoints."""
    resp = client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start_time,
        EndTime=end_time,
        Period=300,
        Statistics=["Average"],
    )

    datapoints = resp.get("Datapoints", [])
    # Sort by timestamp and format
    datapoints.sort(key=lambda dp: dp["Timestamp"])
    return [
        {
            "timestamp": dp["Timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "value": round(dp["Average"], 2),
        }
        for dp in datapoints
    ]


def handle_get_metrics(account: dict, resource: dict) -> dict:
    """Fetch CloudWatch metrics for the last 60 minutes at 5-min intervals.

    Returns CPU and memory utilization metrics for the given resource.
    Returns empty metrics with reason if resource is not running.
    Returns error dict on failure/timeout.

    Args:
        account: Account configuration dict (may contain crossAccountRoleArn).
        resource: Resource dict with id, type, resourceId, and state info.

    Returns:
        dict with resourceId, state, period, timeRange, cpu, and memory arrays.
        On error, returns dict with "error" key and status code 503.
    """
    resource_id = resource.get("id", "unknown")
    resource_state = resource.get("state", "unknown")

    # If resource is not running, return empty metrics with reason
    if resource_state != "running":
        return {
            "resourceId": resource_id,
            "state": resource_state,
            "period": 300,
            "timeRange": "60m",
            "cpu": [],
            "memory": [],
            "reason": f"Resource is {resource_state}",
        }

    # Get metric dimensions for this resource type
    metric_config = _get_metric_dimensions(resource)
    if metric_config is None:
        return {
            "resourceId": resource_id,
            "state": resource_state,
            "period": 300,
            "timeRange": "60m",
            "cpu": [],
            "memory": [],
            "reason": f"Metrics not supported for resource type: {resource.get('type')}",
        }

    try:
        client = _get_cloudwatch_client(account)

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=60)

        # Query CPU utilization
        cpu_data = _query_metric(
            client,
            metric_config["cpu_namespace"],
            metric_config["cpu_metric_name"],
            metric_config["cpu_dimensions"],
            start_time,
            end_time,
        )

        # Query memory utilization (only for EC2 and ECS)
        memory_data = []
        if metric_config["supports_memory"]:
            memory_data = _query_metric(
                client,
                metric_config["memory_namespace"],
                metric_config["memory_metric_name"],
                metric_config["memory_dimensions"],
                start_time,
                end_time,
            )

        result = {
            "resourceId": resource_id,
            "state": resource_state,
            "period": 300,
            "timeRange": "60m",
            "cpu": cpu_data,
            "memory": memory_data,
        }

        return result

    except (ClientError, Exception) as e:
        logger.error(f"[METRICS] Failed to fetch metrics for resource {resource_id}: {e!s}")
        return {"error": "Metrics temporarily unavailable", "status_code": 503}
