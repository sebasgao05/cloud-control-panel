"""
Unit tests for the metrics endpoint (backend/metrics.py).

Tests cover:
- Empty metrics response for non-running resources
- Cross-account CloudWatch client creation
- CPU/memory metric queries for different resource types
- Error handling (timeout, ClientError)
- Metrics route integration via app.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from metrics import handle_get_metrics, _get_metric_dimensions, _get_cloudwatch_client


class TestGetMetricDimensions:
    """Test _get_metric_dimensions returns correct CloudWatch config per resource type."""

    def test_ec2_dimensions(self):
        resource = {"type": "ec2", "resourceId": "i-0abc123def456"}
        result = _get_metric_dimensions(resource)
        assert result["cpu_namespace"] == "AWS/EC2"
        assert result["cpu_metric_name"] == "CPUUtilization"
        assert result["cpu_dimensions"] == [{"Name": "InstanceId", "Value": "i-0abc123def456"}]
        assert result["supports_memory"] is True
        assert result["memory_namespace"] == "CWAgent"
        assert result["memory_metric_name"] == "mem_used_percent"

    def test_ecs_dimensions(self):
        resource = {"type": "ecs", "resourceId": "prod-cluster/web-service"}
        result = _get_metric_dimensions(resource)
        assert result["cpu_namespace"] == "AWS/ECS"
        assert result["cpu_metric_name"] == "CPUUtilization"
        assert result["cpu_dimensions"] == [
            {"Name": "ClusterName", "Value": "prod-cluster"},
            {"Name": "ServiceName", "Value": "web-service"},
        ]
        assert result["supports_memory"] is True
        assert result["memory_namespace"] == "AWS/ECS"
        assert result["memory_metric_name"] == "MemoryUtilization"

    def test_rds_dimensions(self):
        resource = {"type": "rds", "resourceId": "my-db-instance"}
        result = _get_metric_dimensions(resource)
        assert result["cpu_namespace"] == "AWS/RDS"
        assert result["cpu_dimensions"] == [{"Name": "DBInstanceIdentifier", "Value": "my-db-instance"}]
        assert result["supports_memory"] is False

    def test_lightsail_dimensions(self):
        resource = {"type": "lightsail", "resourceId": "my-lightsail-instance"}
        result = _get_metric_dimensions(resource)
        assert result["cpu_namespace"] == "AWS/Lightsail"
        assert result["cpu_dimensions"] == [{"Name": "InstanceName", "Value": "my-lightsail-instance"}]
        assert result["supports_memory"] is False

    def test_apprunner_dimensions(self):
        resource = {"type": "apprunner", "resourceId": "arn:aws:apprunner:us-east-1:123:service/my-svc/abc"}
        result = _get_metric_dimensions(resource)
        assert result["cpu_namespace"] == "AWS/AppRunner"
        assert result["cpu_dimensions"] == [
            {"Name": "ServiceArn", "Value": "arn:aws:apprunner:us-east-1:123:service/my-svc/abc"}
        ]
        assert result["supports_memory"] is False

    def test_unsupported_type_returns_none(self):
        resource = {"type": "unknown-service", "resourceId": "something"}
        result = _get_metric_dimensions(resource)
        assert result is None


class TestHandleGetMetricsNotRunning:
    """Test that non-running resources return empty metrics with reason."""

    def test_stopped_resource(self):
        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "web-server-1", "type": "ec2", "resourceId": "i-0abc", "state": "stopped"}
        result = handle_get_metrics(account, resource)
        assert result["resourceId"] == "web-server-1"
        assert result["state"] == "stopped"
        assert result["cpu"] == []
        assert result["memory"] == []
        assert result["reason"] == "Resource is stopped"
        assert result["period"] == 300
        assert result["timeRange"] == "60m"

    def test_pending_resource(self):
        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "db-1", "type": "rds", "resourceId": "mydb", "state": "pending"}
        result = handle_get_metrics(account, resource)
        assert result["reason"] == "Resource is pending"
        assert result["cpu"] == []
        assert result["memory"] == []

    def test_unknown_state_resource(self):
        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "svc-1", "type": "ecs", "resourceId": "cluster/svc", "state": "unknown"}
        result = handle_get_metrics(account, resource)
        assert result["reason"] == "Resource is unknown"


class TestHandleGetMetricsRunning:
    """Test metric fetching for running resources."""

    @patch("metrics.boto3.client")
    def test_ec2_cpu_and_memory(self, mock_boto_client):
        """Test that EC2 resources query both CPU and memory metrics."""
        now = datetime.now(timezone.utc)
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        # CPU response
        mock_cw.get_metric_statistics.side_effect = [
            {
                "Datapoints": [
                    {"Timestamp": now - timedelta(minutes=10), "Average": 45.234},
                    {"Timestamp": now - timedelta(minutes=5), "Average": 42.876},
                ]
            },
            # Memory response
            {
                "Datapoints": [
                    {"Timestamp": now - timedelta(minutes=10), "Average": 68.123},
                ]
            },
        ]

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "web-1", "type": "ec2", "resourceId": "i-0abc123", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert result["resourceId"] == "web-1"
        assert result["state"] == "running"
        assert result["period"] == 300
        assert result["timeRange"] == "60m"
        assert len(result["cpu"]) == 2
        assert result["cpu"][0]["value"] == 45.23
        assert result["cpu"][1]["value"] == 42.88
        assert len(result["memory"]) == 1
        assert result["memory"][0]["value"] == 68.12

    @patch("metrics.boto3.client")
    def test_rds_no_memory(self, mock_boto_client):
        """Test that RDS resources only query CPU (no memory support)."""
        now = datetime.now(timezone.utc)
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        mock_cw.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Timestamp": now - timedelta(minutes=5), "Average": 30.5},
            ]
        }

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "db-1", "type": "rds", "resourceId": "mydb", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert len(result["cpu"]) == 1
        assert result["memory"] == []
        # get_metric_statistics should only be called once (CPU only)
        assert mock_cw.get_metric_statistics.call_count == 1

    @patch("metrics.boto3.client")
    def test_ecs_cpu_and_memory(self, mock_boto_client):
        """Test that ECS resources query both CPU and memory."""
        now = datetime.now(timezone.utc)
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        mock_cw.get_metric_statistics.side_effect = [
            {"Datapoints": [{"Timestamp": now, "Average": 55.0}]},
            {"Datapoints": [{"Timestamp": now, "Average": 72.5}]},
        ]

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "svc-1", "type": "ecs", "resourceId": "cluster/service", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert len(result["cpu"]) == 1
        assert len(result["memory"]) == 1
        assert mock_cw.get_metric_statistics.call_count == 2


class TestHandleGetMetricsErrors:
    """Test error handling in the metrics endpoint."""

    @patch("metrics.boto3.client")
    def test_cloudwatch_client_error_returns_503(self, mock_boto_client):
        """Test that CloudWatch errors return appropriate error dict."""
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        mock_cw.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "InternalServiceError", "Message": "Service unavailable"}},
            "GetMetricStatistics",
        )

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "web-1", "type": "ec2", "resourceId": "i-0abc", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert "error" in result
        assert result["error"] == "Metrics temporarily unavailable"
        assert result["status_code"] == 503

    @patch("metrics.boto3.client")
    def test_timeout_returns_503(self, mock_boto_client):
        """Test that timeout exceptions return appropriate error dict."""
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        from botocore.exceptions import ReadTimeoutError

        mock_cw.get_metric_statistics.side_effect = ReadTimeoutError(endpoint_url="https://monitoring.us-east-1.amazonaws.com")

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "web-1", "type": "ec2", "resourceId": "i-0abc", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert "error" in result
        assert result["error"] == "Metrics temporarily unavailable"

    @patch("metrics.boto3.client")
    def test_generic_exception_returns_503(self, mock_boto_client):
        """Test that any unhandled exception returns 503 without exposing internals."""
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        mock_cw.get_metric_statistics.side_effect = Exception("Unexpected internal failure")

        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "web-1", "type": "ec2", "resourceId": "i-0abc", "state": "running"}

        result = handle_get_metrics(account, resource)

        assert "error" in result
        assert result["error"] == "Metrics temporarily unavailable"
        # Should not expose internal details
        assert "Unexpected internal failure" not in result["error"]


class TestCrossAccountClient:
    """Test cross-account CloudWatch client creation."""

    @patch("metrics.boto3.client")
    def test_no_role_arn_uses_default_credentials(self, mock_boto_client):
        """Test that accounts without crossAccountRoleArn use default credentials."""
        account = {"id": "acc-1", "region": "us-west-2"}
        _get_cloudwatch_client(account)

        mock_boto_client.assert_called_once()
        call_args = mock_boto_client.call_args
        assert call_args[0][0] == "cloudwatch"
        assert call_args[1]["region_name"] == "us-west-2"
        assert "aws_access_key_id" not in call_args[1]
        assert "aws_secret_access_key" not in call_args[1]
        assert "aws_session_token" not in call_args[1]

    @patch("metrics.boto3.client")
    def test_role_arn_uses_assumed_credentials(self, mock_boto_client):
        """Test that accounts with crossAccountRoleArn use STS AssumeRole."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        account = {
            "id": "acc-2",
            "region": "eu-west-1",
            "crossAccountRoleArn": "arn:aws:iam::999999999999:role/CrossAccountRole",
        }
        _get_cloudwatch_client(account)

        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::999999999999:role/CrossAccountRole",
            RoleSessionName="CloudControlPanel",
            DurationSeconds=3600,
        )

        # The cloudwatch client should be created with the assumed credentials
        cw_call = mock_boto_client.call_args_list[-1]
        assert cw_call[1].get("aws_access_key_id") == "AKID"
        assert cw_call[1].get("aws_secret_access_key") == "SECRET"
        assert cw_call[1].get("aws_session_token") == "TOKEN"
