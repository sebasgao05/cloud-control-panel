"""
Cloud Control Panel - AppRunner Resource Adapter.

Implements the ResourceAdapter interface for AWS App Runner services,
providing start (resume), stop (pause), and status operations with
idempotent checks and cross-account support.
"""

import boto3
from botocore.exceptions import ClientError

from resource_adapter import NormalizedState, ResourceAdapter
from utils import REGION, logger

# AppRunner status → normalized state mapping
APPRUNNER_STATE_MAP: dict[str, NormalizedState] = {
    "RUNNING": "running",
    "PAUSED": "stopped",
    "CREATE_FAILED": "unknown",
    "DELETED": "unknown",
    "DELETE_FAILED": "unknown",
}


class AppRunnerAdapter(ResourceAdapter):
    """Adapter for AppRunner service resume/pause/status operations."""

    def _get_client(self):
        """Create an AppRunner boto3 client with cross-account support."""
        region = self.account.get("region", REGION)
        creds = self._get_credentials()
        if creds:
            return boto3.client("apprunner", region_name=region, **creds)
        return boto3.client("apprunner", region_name=region)

    def start(self) -> dict:
        """Resume the AppRunner service.

        Performs an idempotent check: if the service is already running,
        returns success without invoking the AppRunner API.
        """
        service_arn = self.resource["resourceId"]
        current_status = self._get_service_status()

        normalized = self._normalize_state(current_status)

        if normalized == "running":
            logger.info(f"[APPRUNNER] Service {service_arn} already running, skipping start")
            return {
                "status": "success",
                "message": "Resource already running",
                "resourceId": service_arn,
                "state": "running",
            }

        try:
            self.client.resume_service(ServiceArn=service_arn)
            logger.info(f"[APPRUNNER] Resumed service {service_arn}")
            return {
                "status": "success",
                "message": "Service resuming",
                "resourceId": service_arn,
                "state": "pending",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[APPRUNNER] resume_service failed for {service_arn}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"AppRunner start failed for {service_arn}: {error_code}",
                "resourceId": service_arn,
                "service": "apprunner",
            }

    def stop(self) -> dict:
        """Pause the AppRunner service.

        Performs an idempotent check: if the service is already paused,
        returns success without invoking the AppRunner API.
        """
        service_arn = self.resource["resourceId"]
        current_status = self._get_service_status()

        normalized = self._normalize_state(current_status)

        if normalized == "stopped":
            logger.info(f"[APPRUNNER] Service {service_arn} already stopped, skipping stop")
            return {
                "status": "success",
                "message": "Resource already stopped",
                "resourceId": service_arn,
                "state": "stopped",
            }

        try:
            self.client.pause_service(ServiceArn=service_arn)
            logger.info(f"[APPRUNNER] Paused service {service_arn}")
            return {
                "status": "success",
                "message": "Service pausing",
                "resourceId": service_arn,
                "state": "stopping",
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[APPRUNNER] pause_service failed for {service_arn}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"AppRunner stop failed for {service_arn}: {error_code}",
                "resourceId": service_arn,
                "service": "apprunner",
            }

    def status(self) -> dict:
        """Get the current status of the AppRunner service.

        Calls describe_service and maps the AppRunner status to a normalized state.
        For OPERATION_IN_PROGRESS, determines context from the latest operation.
        """
        service_arn = self.resource["resourceId"]
        try:
            raw_status = self._get_service_status()
            normalized = self._normalize_state(raw_status)
            return {
                "status": "success",
                "resourceId": service_arn,
                "state": normalized,
                "rawState": raw_status,
            }
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(f"[APPRUNNER] describe_service failed for {service_arn}: {error_code} - {error_message}")
            return {
                "status": "error",
                "message": f"AppRunner status check failed for {service_arn}: {error_code}",
                "resourceId": service_arn,
                "state": "unknown",
                "service": "apprunner",
            }

    def _get_service_status(self) -> str:
        """Retrieve the raw AppRunner service status string.

        Returns the service Status field (e.g., 'RUNNING', 'PAUSED',
        'OPERATION_IN_PROGRESS').
        Raises ClientError if the describe_service call fails.
        """
        service_arn = self.resource["resourceId"]
        resp = self.client.describe_service(ServiceArn=service_arn)
        return resp["Service"]["Status"]

    def _normalize_state(self, raw_status: str) -> NormalizedState:
        """Map AppRunner status to normalized state.

        For OPERATION_IN_PROGRESS, inspects the latest operation type to
        determine whether the service is transitioning to running (pending)
        or to stopped (stopping). Defaults to 'pending' if context is
        indeterminate.
        """
        if raw_status in APPRUNNER_STATE_MAP:
            return APPRUNNER_STATE_MAP[raw_status]

        if raw_status == "OPERATION_IN_PROGRESS":
            return self._resolve_in_progress_state()

        return "unknown"

    def _resolve_in_progress_state(self) -> NormalizedState:
        """Determine the transitional state for OPERATION_IN_PROGRESS.

        Calls describe_service to check the latest operation type.
        If the operation is PAUSE_SERVICE → 'stopping'.
        If the operation is RESUME_SERVICE → 'pending'.
        Defaults to 'pending' if unable to determine.
        """
        service_arn = self.resource["resourceId"]
        try:
            resp = self.client.describe_service(ServiceArn=service_arn)
            service = resp["Service"]

            # Check the latest operation to determine direction
            _ = service.get("ServiceObservabilityConfiguration") or {}
            # The LatestOperationId or AutoDeploymentsEnabled won't help directly,
            # but we can inspect the service's operational context via
            # the OperationId or Status metadata.
            # AppRunner provides the latest operation in the Service response.
            operation_type = (
                service.get("LatestOperation", {}).get("OperationType", "") if "LatestOperation" in service else ""
            )

            if operation_type == "PAUSE_SERVICE":
                return "stopping"
            elif operation_type == "RESUME_SERVICE":
                return "pending"

            # Fallback: default to pending for any in-progress state
            return "pending"
        except ClientError:
            # If we can't determine context, default to pending
            return "pending"
