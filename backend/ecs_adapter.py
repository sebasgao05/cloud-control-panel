"""
Cloud Control Panel - ECS Resource Adapter.

Implements start, stop, and status operations for ECS services.
Start sets the service desiredCount to the resource's targetCount (1-10).
Stop sets the service desiredCount to 0.

State mapping:
    desiredCount > 0 & runningCount > 0  → running
    desiredCount == 0                     → stopped
    PROVISIONING, PENDING                 → pending
    DRAINING, DEPROVISIONING              → stopping
    (other)                               → unknown
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from resource_adapter import NormalizedState, ResourceAdapter
from utils import REGION, logger

# 30-second timeout for all ECS API calls
ECS_BOTO_CONFIG = Config(
    connect_timeout=30,
    read_timeout=30,
    retries={"max_attempts": 1},
)


def _parse_ecs_resource_id(resource_id: str) -> tuple[str, str]:
    """Parse the cluster and service names from a resourceId.

    The resourceId can be:
    - An ECS service ARN: arn:aws:ecs:region:account:service/cluster-name/service-name
    - A cluster/service pair: "cluster-name/service-name"

    Returns:
        (cluster_name, service_name) tuple
    """
    if resource_id.startswith("arn:aws:ecs:"):
        # ARN format: arn:aws:ecs:region:account:service/cluster/service-name
        # The part after "service/" contains cluster/service-name
        parts = resource_id.split("/")
        if len(parts) >= 3:
            return parts[-2], parts[-1]
        # Fallback: single service name after service/
        return "default", parts[-1]
    elif "/" in resource_id:
        # cluster-name/service-name format
        parts = resource_id.split("/", 1)
        return parts[0], parts[1]
    else:
        # Just a service name, assume default cluster
        return "default", resource_id


def normalize_ecs_state(
    desired_count: int, running_count: int, task_states: list[str] | None = None
) -> NormalizedState:
    """Normalize ECS service state based on desiredCount and runningCount.

    Args:
        desired_count: The service's desiredCount value.
        running_count: The service's runningCount value.
        task_states: Optional list of individual task last statuses.

    Returns:
        A normalized state string.
    """
    if desired_count == 0:
        if running_count > 0:
            return "stopping"
        return "stopped"

    if desired_count > 0 and running_count > 0:
        return "running"

    # desiredCount > 0 but runningCount == 0: transitional state
    # Check task-level states if available
    if task_states:
        transitional_pending = {"PROVISIONING", "PENDING", "ACTIVATING"}
        transitional_stopping = {"DRAINING", "DEPROVISIONING", "DEACTIVATING"}

        if any(s.upper() in transitional_stopping for s in task_states):
            return "stopping"
        if any(s.upper() in transitional_pending for s in task_states):
            return "pending"

    # Default: desiredCount > 0 but no tasks running yet
    return "pending"


class ECSAdapter(ResourceAdapter):
    """Adapter for ECS service start/stop/status operations."""

    def _get_client(self):
        """Create an ECS boto3 client with cross-account support and 30s timeout."""
        region = self.account.get("region", REGION)
        creds = self._get_credentials()

        if creds:
            return boto3.client(
                "ecs",
                region_name=region,
                config=ECS_BOTO_CONFIG,
                **creds,
            )
        return boto3.client("ecs", region_name=region, config=ECS_BOTO_CONFIG)

    def start(self) -> dict:
        """Start the ECS service by setting desiredCount to targetCount.

        Performs an idempotent check: if already running, returns success
        without invoking the API.

        Returns:
            dict with keys: state, message, resourceId
        """
        resource_id = self.resource["resourceId"]
        cluster_name, service_name = _parse_ecs_resource_id(resource_id)
        target_count = self.resource.get("targetCount", 1)

        # Idempotent check: skip if already running
        current = self.status()
        if current["state"] == "running":
            return {
                "state": "running",
                "message": "Resource already running",
                "resourceId": resource_id,
            }

        try:
            self.client.update_service(
                cluster=cluster_name,
                service=service_name,
                desiredCount=target_count,
            )
            logger.info(f"[ECS] UpdateService: {cluster_name}/{service_name} desiredCount={target_count}")

            return {
                "state": "pending",
                "message": "Service starting",
                "resourceId": resource_id,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[ECS] Start failed for {cluster_name}/{service_name}: {error_code} - {error_message}")
            return {
                "state": "error",
                "message": f"ECS start failed for '{cluster_name}/{service_name}': {error_code}",
                "resourceId": resource_id,
                "error": True,
            }

    def stop(self) -> dict:
        """Stop the ECS service by setting desiredCount to 0.

        Performs an idempotent check: if already stopped, returns success
        without invoking the API.

        Returns:
            dict with keys: state, message, resourceId
        """
        resource_id = self.resource["resourceId"]
        cluster_name, service_name = _parse_ecs_resource_id(resource_id)

        # Idempotent check: skip if already stopped
        current = self.status()
        if current["state"] == "stopped":
            return {
                "state": "stopped",
                "message": "Resource already stopped",
                "resourceId": resource_id,
            }

        try:
            self.client.update_service(
                cluster=cluster_name,
                service=service_name,
                desiredCount=0,
            )
            logger.info(f"[ECS] UpdateService: {cluster_name}/{service_name} desiredCount=0")

            return {
                "state": "stopping",
                "message": "Service stopping",
                "resourceId": resource_id,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[ECS] Stop failed for {cluster_name}/{service_name}: {error_code} - {error_message}")
            return {
                "state": "error",
                "message": f"ECS stop failed for '{cluster_name}/{service_name}': {error_code}",
                "resourceId": resource_id,
                "error": True,
            }

    def status(self) -> dict:
        """Get current ECS service state as a normalized state.

        Calls describe_services and determines state from desiredCount
        and runningCount on the service.

        Returns:
            dict with keys: state (NormalizedState), rawState, resourceId
        """
        resource_id = self.resource["resourceId"]
        cluster_name, service_name = _parse_ecs_resource_id(resource_id)

        try:
            resp = self.client.describe_services(
                cluster=cluster_name,
                services=[service_name],
            )

            services = resp.get("services", [])
            if not services:
                logger.warning(f"[ECS] No service found: {cluster_name}/{service_name}")
                return {
                    "state": "unknown",
                    "rawState": "not_found",
                    "resourceId": resource_id,
                }

            service = services[0]
            desired_count = service.get("desiredCount", 0)
            running_count = service.get("runningCount", 0)

            normalized = normalize_ecs_state(desired_count, running_count)

            raw_state = f"desired={desired_count},running={running_count}"

            return {
                "state": normalized,
                "rawState": raw_state,
                "resourceId": resource_id,
                "desiredCount": desired_count,
                "runningCount": running_count,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[ECS] Status check failed for {cluster_name}/{service_name}: {error_code} - {error_message}")
            return {
                "state": "unknown",
                "rawState": "error",
                "resourceId": resource_id,
                "error": True,
            }
