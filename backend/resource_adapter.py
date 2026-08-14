"""
Cloud Control Panel - Resource Adapter base class and factory.

Provides a uniform interface (start, stop, status) for all supported resource types
(EC2, RDS, ECS, Lightsail, AppRunner). Includes cross-account STS AssumeRole logic
for operating on resources in external AWS accounts.
"""

from abc import ABC, abstractmethod
from typing import Literal

import boto3
from botocore.exceptions import ClientError

from utils import REGION, logger

NormalizedState = Literal["running", "stopped", "pending", "stopping", "unknown"]


class ResourceAdapter(ABC):
    """Base class for service-specific resource adapters."""

    def __init__(self, account: dict, resource: dict):
        self.account = account
        self.resource = resource
        self.client = self._get_client()

    @abstractmethod
    def _get_client(self):
        """Create the appropriate boto3 client with cross-account support."""
        ...

    @abstractmethod
    def start(self) -> dict:
        """Start the resource. Returns status dict."""
        ...

    @abstractmethod
    def stop(self) -> dict:
        """Stop the resource. Returns status dict."""
        ...

    @abstractmethod
    def status(self) -> dict:
        """Get current resource state as normalized state."""
        ...

    def _get_credentials(self) -> dict | None:
        """Get cross-account credentials via STS AssumeRole.

        Returns a dict with aws_access_key_id, aws_secret_access_key, and
        aws_session_token if a crossAccountRoleArn is configured. Returns None
        if no cross-account role is set (use default Lambda credentials).

        Raises:
            PermissionError: When AssumeRole fails with AccessDenied.
            RuntimeError: When AssumeRole fails with ExpiredToken.
            Exception: For any other AssumeRole failure.
        """
        role_arn = self.account.get("crossAccountRoleArn")
        if not role_arn:
            return None

        region = self.account.get("region", REGION)
        sts = boto3.client("sts", region_name=region)

        try:
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="CloudControlPanel",
                DurationSeconds=3600,
            )["Credentials"]
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            account_id = self.account.get("id", "unknown")

            if error_code == "AccessDenied":
                logger.error(
                    f"[CROSS-ACCOUNT] AccessDenied assuming role {role_arn} "
                    f"for account {account_id}"
                )
                raise PermissionError(
                    f"Cross-account access denied for account {account_id}"
                ) from e

            if error_code == "ExpiredTokenException" or error_code == "ExpiredToken":
                logger.error(
                    f"[CROSS-ACCOUNT] ExpiredToken assuming role {role_arn} "
                    f"for account {account_id}"
                )
                raise RuntimeError(
                    f"Cross-account session expired for account {account_id}"
                ) from e

            # All other AssumeRole failures
            error_message = e.response["Error"].get("Message", str(e))
            logger.error(
                f"[CROSS-ACCOUNT] AssumeRole failed for account {account_id}: "
                f"{error_code} - {error_message}"
            )
            raise Exception(
                f"Cross-account access failed for account {account_id}: {error_code}"
            ) from e

        return {
            "aws_access_key_id": creds["AccessKeyId"],
            "aws_secret_access_key": creds["SecretAccessKey"],
            "aws_session_token": creds["SessionToken"],
        }


def get_adapter(account: dict, resource: dict) -> "ResourceAdapter":
    """Factory: return the correct adapter based on resource type.

    Uses lazy imports to avoid circular dependencies since adapter classes
    are defined in separate modules.

    Args:
        account: Account configuration dict.
        resource: Resource configuration dict with a 'type' field.

    Returns:
        An instance of the appropriate ResourceAdapter subclass.

    Raises:
        ValueError: If the resource type is not supported.
    """
    resource_type = resource.get("type", "ec2")

    # Lazy imports to avoid circular dependencies - adapter modules
    # import this base class, so we import them only when needed.
    if resource_type == "ec2":
        from ec2_adapter import EC2Adapter
        return EC2Adapter(account, resource)
    elif resource_type == "rds":
        from rds_adapter import RDSAdapter
        return RDSAdapter(account, resource)
    elif resource_type == "ecs":
        from ecs_adapter import ECSAdapter
        return ECSAdapter(account, resource)
    elif resource_type == "lightsail":
        from lightsail_adapter import LightsailAdapter
        return LightsailAdapter(account, resource)
    elif resource_type == "apprunner":
        from apprunner_adapter import AppRunnerAdapter
        return AppRunnerAdapter(account, resource)
    else:
        raise ValueError(f"Unsupported resource type: {resource_type}")
