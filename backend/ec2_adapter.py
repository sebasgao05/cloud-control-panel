"""
Cloud Control Panel - EC2 Resource Adapter.

Implements the ResourceAdapter interface for Amazon EC2 instances,
providing start, stop, and status operations with idempotent checks
and cross-account support.
"""

import boto3
from botocore.exceptions import ClientError

from resource_adapter import NormalizedState, ResourceAdapter
from utils import REGION, logger

# EC2 state → normalized state mapping
EC2_STATE_MAP: dict[str, NormalizedState] = {
    "running": "running",
    "stopped": "stopped",
    "pending": "pending",
    "stopping": "stopping",
    "shutting-down": "stopping",
}


class EC2Adapter(ResourceAdapter):
    """Adapter for EC2 instance start/stop/status operations."""

    def _get_client(self):
        """Create an EC2 boto3 client with cross-account support."""
        region = self.account.get("region", REGION)
        creds = self._get_credentials()
        if creds:
            return boto3.client("ec2", region_name=region, **creds)
        return boto3.client("ec2", region_name=region)

    def start(self) -> dict:
        """Start the EC2 instance.

        Performs an idempotent check: if the instance is already running,
        returns success without invoking the EC2 API.
        """
        instance_id = self.resource["resourceId"]
        current = self._get_instance_state()
        normalized = EC2_STATE_MAP.get(current, "unknown")

        if normalized == "running":
            logger.info(
                f"[EC2] Instance {instance_id} already running, skipping start"
            )
            return {
                "status": "success",
                "message": "Resource already running",
                "resourceId": instance_id,
                "state": "running",
            }

        try:
            self.client.start_instances(InstanceIds=[instance_id])
            logger.info(f"[EC2] Started instance {instance_id}")
            return {
                "status": "success",
                "message": "Instance starting",
                "resourceId": instance_id,
                "state": "pending",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[EC2] start_instances failed for {instance_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "status": "error",
                "message": f"EC2 start failed for {instance_id}: {error_code}",
                "resourceId": instance_id,
                "service": "ec2",
            }

    def stop(self) -> dict:
        """Stop the EC2 instance.

        Performs an idempotent check: if the instance is already stopped,
        returns success without invoking the EC2 API.
        """
        instance_id = self.resource["resourceId"]
        current = self._get_instance_state()
        normalized = EC2_STATE_MAP.get(current, "unknown")

        if normalized == "stopped":
            logger.info(
                f"[EC2] Instance {instance_id} already stopped, skipping stop"
            )
            return {
                "status": "success",
                "message": "Resource already stopped",
                "resourceId": instance_id,
                "state": "stopped",
            }

        try:
            self.client.stop_instances(InstanceIds=[instance_id])
            logger.info(f"[EC2] Stopped instance {instance_id}")
            return {
                "status": "success",
                "message": "Instance stopping",
                "resourceId": instance_id,
                "state": "stopping",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[EC2] stop_instances failed for {instance_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "status": "error",
                "message": f"EC2 stop failed for {instance_id}: {error_code}",
                "resourceId": instance_id,
                "service": "ec2",
            }

    def status(self) -> dict:
        """Get the current status of the EC2 instance.

        Calls describe_instances and maps the EC2 state to a normalized state.
        """
        instance_id = self.resource["resourceId"]
        try:
            current = self._get_instance_state()
            normalized = EC2_STATE_MAP.get(current, "unknown")
            return {
                "status": "success",
                "resourceId": instance_id,
                "state": normalized,
                "rawState": current,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[EC2] describe_instances failed for {instance_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "status": "error",
                "message": f"EC2 status check failed for {instance_id}: {error_code}",
                "resourceId": instance_id,
                "state": "unknown",
                "service": "ec2",
            }

    def _get_instance_state(self) -> str:
        """Retrieve the raw EC2 instance state name.

        Returns the EC2 state name string (e.g., 'running', 'stopped').
        Raises ClientError if the describe_instances call fails.
        """
        instance_id = self.resource["resourceId"]
        resp = self.client.describe_instances(InstanceIds=[instance_id])
        instance = resp["Reservations"][0]["Instances"][0]
        return instance["State"]["Name"]
