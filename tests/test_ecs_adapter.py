"""
Tests for the ECS Resource Adapter.

Validates:
- Correct parsing of ECS resourceId (ARN and cluster/service format)
- Start sets desiredCount to targetCount (1-10)
- Stop sets desiredCount to 0
- State normalization based on desiredCount and runningCount
- Idempotent start/stop behavior
- Error handling with 30-second timeout configuration
- Cross-account credential usage

Requirements: 2.3, 2.4, 2.9, 2.10, 2.11
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from ecs_adapter import (
    ECS_BOTO_CONFIG,
    ECSAdapter,
    _parse_ecs_resource_id,
    normalize_ecs_state,
)


# --- Fixtures ---


@pytest.fixture
def account():
    """Standard account without cross-account role."""
    return {"id": "acc-1", "region": "us-east-1"}


@pytest.fixture
def cross_account():
    """Account with cross-account role configured."""
    return {
        "id": "acc-2",
        "region": "eu-west-1",
        "crossAccountRoleArn": "arn:aws:iam::123456789012:role/CrossRole",
    }


@pytest.fixture
def ecs_resource():
    """ECS service resource with cluster/service format."""
    return {
        "id": "res-ecs-1",
        "type": "ecs",
        "resourceId": "prod-cluster/web-service",
        "targetCount": 3,
    }


@pytest.fixture
def ecs_resource_arn():
    """ECS service resource with ARN format."""
    return {
        "id": "res-ecs-2",
        "type": "ecs",
        "resourceId": "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/api-service",
        "targetCount": 2,
    }


@pytest.fixture
def ecs_resource_no_target():
    """ECS service resource without targetCount (defaults to 1)."""
    return {
        "id": "res-ecs-3",
        "type": "ecs",
        "resourceId": "staging-cluster/worker-service",
    }


# --- Tests for _parse_ecs_resource_id ---


class TestParseEcsResourceId:
    """Tests for parsing ECS resource identifiers."""

    def test_parses_cluster_service_format(self):
        """Parses 'cluster-name/service-name' format correctly."""
        cluster, service = _parse_ecs_resource_id("prod-cluster/web-service")
        assert cluster == "prod-cluster"
        assert service == "web-service"

    def test_parses_arn_format(self):
        """Parses full ECS service ARN correctly."""
        arn = "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/api-service"
        cluster, service = _parse_ecs_resource_id(arn)
        assert cluster == "my-cluster"
        assert service == "api-service"

    def test_parses_service_name_only(self):
        """Plain service name defaults to 'default' cluster."""
        cluster, service = _parse_ecs_resource_id("my-service")
        assert cluster == "default"
        assert service == "my-service"

    def test_parses_cluster_with_hyphens(self):
        """Handles cluster and service names with hyphens."""
        cluster, service = _parse_ecs_resource_id("my-prod-cluster/my-web-service")
        assert cluster == "my-prod-cluster"
        assert service == "my-web-service"


# --- Tests for normalize_ecs_state ---


class TestNormalizeEcsState:
    """Tests for ECS state normalization."""

    def test_running_when_desired_and_running_both_positive(self):
        """State is 'running' when desiredCount > 0 and runningCount > 0."""
        assert normalize_ecs_state(3, 3) == "running"
        assert normalize_ecs_state(5, 2) == "running"
        assert normalize_ecs_state(1, 1) == "running"

    def test_stopped_when_desired_is_zero_and_running_is_zero(self):
        """State is 'stopped' when desiredCount == 0 and runningCount == 0."""
        assert normalize_ecs_state(0, 0) == "stopped"

    def test_stopping_when_desired_zero_but_running_positive(self):
        """State is 'stopping' when desiredCount == 0 but tasks still running."""
        assert normalize_ecs_state(0, 3) == "stopping"
        assert normalize_ecs_state(0, 1) == "stopping"

    def test_pending_when_desired_positive_but_running_zero(self):
        """State is 'pending' when desiredCount > 0 but runningCount == 0."""
        assert normalize_ecs_state(3, 0) == "pending"
        assert normalize_ecs_state(1, 0) == "pending"

    def test_pending_with_provisioning_task_states(self):
        """State is 'pending' when task states include PROVISIONING/PENDING."""
        assert normalize_ecs_state(2, 0, ["PROVISIONING"]) == "pending"
        assert normalize_ecs_state(2, 0, ["PENDING"]) == "pending"

    def test_stopping_with_draining_task_states(self):
        """State is 'stopping' when task states include DRAINING/DEPROVISIONING."""
        assert normalize_ecs_state(2, 0, ["DRAINING"]) == "stopping"
        assert normalize_ecs_state(2, 0, ["DEPROVISIONING"]) == "stopping"


# --- Tests for _get_client ---


class TestECSGetClient:
    """Tests for ECS client creation."""

    @patch("ecs_adapter.boto3.client")
    def test_creates_client_with_default_credentials(self, mock_boto_client, account, ecs_resource):
        """Creates ECS client with Lambda default credentials when no role ARN."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)

        mock_boto_client.assert_called_once_with(
            "ecs",
            region_name="us-east-1",
            config=ECS_BOTO_CONFIG,
        )
        assert adapter.client == mock_client

    @patch("ecs_adapter.boto3.client")
    def test_creates_client_with_cross_account_credentials(self, mock_boto_client, cross_account, ecs_resource):
        """Creates ECS client using STS credentials when role ARN is configured."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA_CROSS",
                "SecretAccessKey": "SECRET_CROSS",
                "SessionToken": "TOKEN_CROSS",
            }
        }
        mock_ecs = MagicMock()

        # First call is STS (from _get_credentials), second is ECS
        mock_boto_client.side_effect = [mock_sts, mock_ecs]

        adapter = ECSAdapter(cross_account, ecs_resource)

        # Verify STS was called first
        assert mock_boto_client.call_args_list[0] == (
            ("sts",),
            {"region_name": "eu-west-1"},
        )
        # Verify ECS client created with cross-account creds
        assert mock_boto_client.call_args_list[1] == (
            ("ecs",),
            {
                "region_name": "eu-west-1",
                "config": ECS_BOTO_CONFIG,
                "aws_access_key_id": "AKIA_CROSS",
                "aws_secret_access_key": "SECRET_CROSS",
                "aws_session_token": "TOKEN_CROSS",
            },
        )

    @patch("ecs_adapter.boto3.client")
    def test_timeout_config_is_30_seconds(self, mock_boto_client, account, ecs_resource):
        """Boto3 Config has 30-second connect and read timeout."""
        mock_boto_client.return_value = MagicMock()

        ECSAdapter(account, ecs_resource)

        call_kwargs = mock_boto_client.call_args[1]
        config = call_kwargs["config"]
        assert config.connect_timeout == 30
        assert config.read_timeout == 30


# --- Tests for start() ---


class TestECSStart:
    """Tests for the ECS start operation."""

    @patch("ecs_adapter.boto3.client")
    def test_start_calls_update_service_with_target_count(self, mock_boto_client, account, ecs_resource):
        """Start calls update_service with configured targetCount."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.start()

        mock_client.update_service.assert_called_once_with(
            cluster="prod-cluster",
            service="web-service",
            desiredCount=3,
        )
        assert result["state"] == "pending"
        assert result["resourceId"] == "prod-cluster/web-service"

    @patch("ecs_adapter.boto3.client")
    def test_start_uses_arn_format_resource_id(self, mock_boto_client, account, ecs_resource_arn):
        """Start correctly parses ARN format to extract cluster and service."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource_arn)
        result = adapter.start()

        mock_client.update_service.assert_called_once_with(
            cluster="my-cluster",
            service="api-service",
            desiredCount=2,
        )
        assert result["state"] == "pending"

    @patch("ecs_adapter.boto3.client")
    def test_start_defaults_target_count_to_1(self, mock_boto_client, account, ecs_resource_no_target):
        """Start defaults desiredCount to 1 when targetCount is not configured."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource_no_target)
        result = adapter.start()

        mock_client.update_service.assert_called_once_with(
            cluster="staging-cluster",
            service="worker-service",
            desiredCount=1,
        )
        assert result["state"] == "pending"

    @patch("ecs_adapter.boto3.client")
    def test_start_idempotent_when_already_running(self, mock_boto_client, account, ecs_resource):
        """Start returns success without API call when already running."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 3, "runningCount": 3}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.start()

        mock_client.update_service.assert_not_called()
        assert result["state"] == "running"
        assert "already" in result["message"].lower()

    @patch("ecs_adapter.boto3.client")
    def test_start_handles_client_error(self, mock_boto_client, account, ecs_resource):
        """Start returns error dict on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_client.update_service.side_effect = ClientError(
            {"Error": {"Code": "ServiceNotFoundException", "Message": "Service not found"}},
            "UpdateService",
        )
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.start()

        assert result["state"] == "error"
        assert result["error"] is True
        assert "ServiceNotFoundException" in result["message"]


# --- Tests for stop() ---


class TestECSStop:
    """Tests for the ECS stop operation."""

    @patch("ecs_adapter.boto3.client")
    def test_stop_calls_update_service_with_zero(self, mock_boto_client, account, ecs_resource):
        """Stop calls update_service with desiredCount=0."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 3, "runningCount": 3}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.stop()

        mock_client.update_service.assert_called_once_with(
            cluster="prod-cluster",
            service="web-service",
            desiredCount=0,
        )
        assert result["state"] == "stopping"
        assert result["resourceId"] == "prod-cluster/web-service"

    @patch("ecs_adapter.boto3.client")
    def test_stop_idempotent_when_already_stopped(self, mock_boto_client, account, ecs_resource):
        """Stop returns success without API call when already stopped."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.stop()

        mock_client.update_service.assert_not_called()
        assert result["state"] == "stopped"
        assert "already" in result["message"].lower()

    @patch("ecs_adapter.boto3.client")
    def test_stop_handles_client_error(self, mock_boto_client, account, ecs_resource):
        """Stop returns error dict on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 3, "runningCount": 3}]
        }
        mock_client.update_service.side_effect = ClientError(
            {"Error": {"Code": "ClusterNotFoundException", "Message": "Cluster not found"}},
            "UpdateService",
        )
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.stop()

        assert result["state"] == "error"
        assert result["error"] is True
        assert "ClusterNotFoundException" in result["message"]


# --- Tests for status() ---


class TestECSStatus:
    """Tests for the ECS status operation."""

    @patch("ecs_adapter.boto3.client")
    def test_status_calls_describe_services(self, mock_boto_client, account, ecs_resource):
        """Status calls describe_services with correct cluster and service."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 3, "runningCount": 3}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.status()

        mock_client.describe_services.assert_called_with(
            cluster="prod-cluster",
            services=["web-service"],
        )
        assert result["state"] == "running"
        assert result["desiredCount"] == 3
        assert result["runningCount"] == 3

    @patch("ecs_adapter.boto3.client")
    def test_status_returns_unknown_when_service_not_found(self, mock_boto_client, account, ecs_resource):
        """Status returns unknown when describe_services returns empty list."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {"services": []}
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.status()

        assert result["state"] == "unknown"
        assert result["rawState"] == "not_found"

    @patch("ecs_adapter.boto3.client")
    @pytest.mark.parametrize(
        "desired,running,expected_state",
        [
            (3, 3, "running"),
            (1, 1, "running"),
            (5, 2, "running"),
            (0, 0, "stopped"),
            (0, 3, "stopping"),
            (0, 1, "stopping"),
            (3, 0, "pending"),
            (1, 0, "pending"),
        ],
    )
    def test_state_normalization(
        self, mock_boto_client, account, ecs_resource, desired, running, expected_state
    ):
        """Each desiredCount/runningCount combination maps to correct normalized state."""
        mock_client = MagicMock()
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": desired, "runningCount": running}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.status()

        assert result["state"] == expected_state

    @patch("ecs_adapter.boto3.client")
    def test_status_handles_client_error(self, mock_boto_client, account, ecs_resource):
        """Status returns unknown state on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_services.side_effect = ClientError(
            {"Error": {"Code": "ClusterNotFoundException", "Message": "Not found"}},
            "DescribeServices",
        )
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, ecs_resource)
        result = adapter.status()

        assert result["state"] == "unknown"
        assert result["rawState"] == "error"
        assert result["error"] is True
