"""
Cloud Control Panel - Lightsail Resource Adapter.

Implements the ResourceAdapter interface for Amazon Lightsail instances,
providing start, stop, and status operations with idempotent checks
and cross-account support.
"""

import boto3
from botocore.exceptions import ClientError

from resource_adapter import NormalizedState, ResourceAdapter
from utils import REGION, logger

# Lightsail state → normalized state mapping
LIGHTSAIL_STATE_MAP: dict[str, NormalizedState] = {
    "running": "running",
    "stopped": "stopped",
    "pending": "pending",
    "stopping": "stopping",
}


class LightsailAdapter(ResourceAdapter):
    """Adapter for Lightsail instance start/stop/status operations."""

    def _get_client(self):
        """Create a Lightsail boto3 client with cross-account support."""
        region = self.account.get("region", REGION)
        creds = self._get_credentials()
        if creds:
            return boto3.client("lightsail", region_name=region, **creds)
        return boto3.client("lightsail", region_name=region)

    def start(self) -> dict:
        """Start the Lightsail instance.

        Performs an idempotent check: if the instance is already running,
        returns success without invoking the Lightsail API.
        """
        instance_name = self.resource["resourceId"]
        current = self._get_instance_state()
        normalized = LIGHTSAIL_STATE_MAP.get(current, "unknown")

        if normalized == "running":
            logger.info(f"[LIGHTSAIL] Instance {instance_name} already running, skipping start")
            return {
                "status": "success",
                "message": "Resource already running",
                "resourceId": instance_name,
                "state": "running",
            }

        try:
            self.client.start_instance(instanceName=instance_name)
            logger.info(f"[LIGHTSAIL] Started instance {instance_name}")
            return {
                "status": "success",
                "message": "Instance starting",
                "resourceId": instance_name,
                "state": "pending",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[LIGHTSAIL] start_instance failed for {instance_name}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"Lightsail start failed for {instance_name}: {error_code}",
                "resourceId": instance_name,
                "service": "lightsail",
            }

    def stop(self) -> dict:
        """Stop the Lightsail instance.

        Performs an idempotent check: if the instance is already stopped,
        returns success without invoking the Lightsail API.
        """
        instance_name = self.resource["resourceId"]
        current = self._get_instance_state()
        normalized = LIGHTSAIL_STATE_MAP.get(current, "unknown")

        if normalized == "stopped":
            logger.info(f"[LIGHTSAIL] Instance {instance_name} already stopped, skipping stop")
            return {
                "status": "success",
                "message": "Resource already stopped",
                "resourceId": instance_name,
                "state": "stopped",
            }

        try:
            self.client.stop_instance(instanceName=instance_name)
            logger.info(f"[LIGHTSAIL] Stopped instance {instance_name}")
            return {
                "status": "success",
                "message": "Instance stopping",
                "resourceId": instance_name,
                "state": "stopping",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[LIGHTSAIL] stop_instance failed for {instance_name}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"Lightsail stop failed for {instance_name}: {error_code}",
                "resourceId": instance_name,
                "service": "lightsail",
            }

    def status(self) -> dict:
        """Get the current status of the Lightsail instance.

        Calls get_instance and maps the Lightsail state to a normalized state.
        """
        instance_name = self.resource["resourceId"]
        try:
            current = self._get_instance_state()
            normalized = LIGHTSAIL_STATE_MAP.get(current, "unknown")
            return {
                "status": "success",
                "resourceId": instance_name,
                "state": normalized,
                "rawState": current,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[LIGHTSAIL] get_instance failed for {instance_name}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"Lightsail status check failed for {instance_name}: {error_code}",
                "resourceId": instance_name,
                "state": "unknown",
                "service": "lightsail",
            }

    def _get_instance_state(self) -> str:
        """Retrieve the raw Lightsail instance state name.

        Returns the Lightsail state name string (e.g., 'running', 'stopped').
        Raises ClientError if the get_instance call fails.
        """
        instance_name = self.resource["resourceId"]
        resp = self.client.get_instance(instanceName=instance_name)
        return resp["instance"]["state"]["name"]
