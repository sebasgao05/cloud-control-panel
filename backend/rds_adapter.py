"""
Cloud Control Panel - RDS Resource Adapter.

Implements start, stop, and status operations for RDS clusters and instances.
Dispatches to the correct API based on the resource's `resourceType` field
("cluster" or "instance").

State mapping:
    available  → running
    stopped    → stopped
    starting   → pending
    creating   → pending
    stopping   → stopping
    (other)    → unknown
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from resource_adapter import NormalizedState, ResourceAdapter
from utils import REGION, logger

# RDS-specific state normalization
RDS_STATE_MAP: dict[str, NormalizedState] = {
    "available": "running",
    "stopped": "stopped",
    "starting": "pending",
    "creating": "pending",
    "stopping": "stopping",
}

# 30-second timeout for all RDS API calls
RDS_BOTO_CONFIG = Config(
    connect_timeout=30,
    read_timeout=30,
    retries={"max_attempts": 1},
)


class RDSAdapter(ResourceAdapter):
    """Adapter for RDS cluster and instance operations."""

    def _get_client(self):
        """Create an RDS boto3 client with cross-account support and 30s timeout."""
        region = self.account.get("region", REGION)
        creds = self._get_credentials()

        if creds:
            return boto3.client(
                "rds",
                region_name=region,
                config=RDS_BOTO_CONFIG,
                **creds,
            )
        return boto3.client("rds", region_name=region, config=RDS_BOTO_CONFIG)

    def start(self) -> dict:
        """Start the RDS cluster or instance.

        Performs an idempotent check: if already running, returns success
        without invoking the API.

        Returns:
            dict with keys: state, message, resourceId
        """
        resource_id = self.resource["resourceId"]
        resource_type = self.resource.get("resourceType", "instance")

        # Idempotent check: skip if already running
        current = self.status()
        if current["state"] == "running":
            return {
                "state": "running",
                "message": "Resource already running",
                "resourceId": resource_id,
            }

        try:
            if resource_type == "cluster":
                self.client.start_db_cluster(DBClusterIdentifier=resource_id)
                logger.info(f"[RDS] StartDBCluster: {resource_id}")
            else:
                self.client.start_db_instance(DBInstanceIdentifier=resource_id)
                logger.info(f"[RDS] StartDBInstance: {resource_id}")

            return {
                "state": "pending",
                "message": "Resource starting",
                "resourceId": resource_id,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[RDS] Start failed for {resource_type} {resource_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "state": "error",
                "message": f"RDS start failed for {resource_type} '{resource_id}': {error_code}",
                "resourceId": resource_id,
                "error": True,
            }

    def stop(self) -> dict:
        """Stop the RDS cluster or instance.

        Performs an idempotent check: if already stopped, returns success
        without invoking the API.

        Returns:
            dict with keys: state, message, resourceId
        """
        resource_id = self.resource["resourceId"]
        resource_type = self.resource.get("resourceType", "instance")

        # Idempotent check: skip if already stopped
        current = self.status()
        if current["state"] == "stopped":
            return {
                "state": "stopped",
                "message": "Resource already stopped",
                "resourceId": resource_id,
            }

        try:
            if resource_type == "cluster":
                self.client.stop_db_cluster(DBClusterIdentifier=resource_id)
                logger.info(f"[RDS] StopDBCluster: {resource_id}")
            else:
                self.client.stop_db_instance(DBInstanceIdentifier=resource_id)
                logger.info(f"[RDS] StopDBInstance: {resource_id}")

            return {
                "state": "stopping",
                "message": "Resource stopping",
                "resourceId": resource_id,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[RDS] Stop failed for {resource_type} {resource_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "state": "error",
                "message": f"RDS stop failed for {resource_type} '{resource_id}': {error_code}",
                "resourceId": resource_id,
                "error": True,
            }

    def status(self) -> dict:
        """Get current RDS cluster or instance state as a normalized state.

        Returns:
            dict with keys: state (NormalizedState), rawState, resourceId
        """
        resource_id = self.resource["resourceId"]
        resource_type = self.resource.get("resourceType", "instance")

        try:
            if resource_type == "cluster":
                resp = self.client.describe_db_clusters(
                    DBClusterIdentifier=resource_id
                )
                raw_state = resp["DBClusters"][0]["Status"]
            else:
                resp = self.client.describe_db_instances(
                    DBInstanceIdentifier=resource_id
                )
                raw_state = resp["DBInstances"][0]["DBInstanceStatus"]

            normalized: NormalizedState = RDS_STATE_MAP.get(raw_state, "unknown")

            return {
                "state": normalized,
                "rawState": raw_state,
                "resourceId": resource_id,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[RDS] Status check failed for {resource_type} {resource_id}: "
                f"{error_code} - {error_message}"
            )
            return {
                "state": "unknown",
                "rawState": "error",
                "resourceId": resource_id,
                "error": True,
            }
