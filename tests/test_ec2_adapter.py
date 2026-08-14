"""Tests for backend/ec2_adapter.py - EC2 Resource Adapter."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestEC2AdapterGetClient:
    """Test _get_client with and without cross-account credentials."""

    @patch("ec2_adapter.boto3.client")
    def test_direct_client_no_cross_account(self, mock_client):
        from ec2_adapter import EC2Adapter

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abcdef1234567890"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        mock_client.assert_called_with("ec2", region_name="us-east-1")

    @patch("ec2_adapter.boto3.client")
    def test_cross_account_client(self, mock_client):
        from ec2_adapter import EC2Adapter

        account = {"region": "eu-west-1", "crossAccountRoleArn": "arn:aws:iam::123:role/Test"}
        resource = {"resourceId": "i-0abcdef1234567890"}
        creds = {
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        }

        with patch.object(EC2Adapter, "_get_credentials", return_value=creds):
            adapter = EC2Adapter(account, resource)

        mock_client.assert_called_with(
            "ec2",
            region_name="eu-west-1",
            aws_access_key_id="AKIA...",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )


class TestEC2AdapterStatus:
    """Test status() method."""

    @patch("ec2_adapter.boto3.client")
    def test_status_running(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "running"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert result["rawState"] == "running"

    @patch("ec2_adapter.boto3.client")
    def test_status_stopped(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "stopped"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopped"

    @patch("ec2_adapter.boto3.client")
    def test_status_pending(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "pending"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "pending"

    @patch("ec2_adapter.boto3.client")
    def test_status_shutting_down_maps_to_stopping(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "shutting-down"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopping"

    @patch("ec2_adapter.boto3.client")
    def test_status_unknown_state(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "terminated"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "unknown"

    @patch("ec2_adapter.boto3.client")
    def test_status_api_error(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.side_effect = ClientError(
            {"Error": {"Code": "InvalidInstanceID.NotFound", "Message": "Not found"}},
            "DescribeInstances",
        )
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.status()
        assert result["status"] == "error"
        assert result["state"] == "unknown"
        assert "ec2" in result["service"]


class TestEC2AdapterStart:
    """Test start() method with idempotent checks."""

    @patch("ec2_adapter.boto3.client")
    def test_start_when_stopped(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "stopped"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "pending"
        mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-0abc123"])

    @patch("ec2_adapter.boto3.client")
    def test_start_idempotent_when_already_running(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "running"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert "already running" in result["message"]
        mock_ec2.start_instances.assert_not_called()

    @patch("ec2_adapter.boto3.client")
    def test_start_api_error(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "stopped"}}]}
            ]
        }
        mock_ec2.start_instances.side_effect = ClientError(
            {"Error": {"Code": "IncorrectInstanceState", "Message": "Cannot start"}},
            "StartInstances",
        )
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.start()
        assert result["status"] == "error"
        assert "ec2" in result["service"]


class TestEC2AdapterStop:
    """Test stop() method with idempotent checks."""

    @patch("ec2_adapter.boto3.client")
    def test_stop_when_running(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "running"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopping"
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-0abc123"])

    @patch("ec2_adapter.boto3.client")
    def test_stop_idempotent_when_already_stopped(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "stopped"}}]}
            ]
        }
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopped"
        assert "already stopped" in result["message"]
        mock_ec2.stop_instances.assert_not_called()

    @patch("ec2_adapter.boto3.client")
    def test_stop_api_error(self, mock_boto_client):
        from ec2_adapter import EC2Adapter

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abc123", "State": {"Name": "running"}}]}
            ]
        }
        mock_ec2.stop_instances.side_effect = ClientError(
            {"Error": {"Code": "IncorrectInstanceState", "Message": "Cannot stop"}},
            "StopInstances",
        )
        mock_boto_client.return_value = mock_ec2

        account = {"region": "us-east-1"}
        resource = {"resourceId": "i-0abc123"}

        with patch.object(EC2Adapter, "_get_credentials", return_value=None):
            adapter = EC2Adapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "error"
        assert "ec2" in result["service"]


class TestEC2StateMapping:
    """Test EC2 state to normalized state mapping."""

    def test_state_map_completeness(self):
        from ec2_adapter import EC2_STATE_MAP

        # Verify all expected EC2 states are mapped
        assert EC2_STATE_MAP["running"] == "running"
        assert EC2_STATE_MAP["stopped"] == "stopped"
        assert EC2_STATE_MAP["pending"] == "pending"
        assert EC2_STATE_MAP["stopping"] == "stopping"
        assert EC2_STATE_MAP["shutting-down"] == "stopping"

    def test_state_map_values_are_valid_normalized_states(self):
        from ec2_adapter import EC2_STATE_MAP

        valid_states = {"running", "stopped", "pending", "stopping", "unknown"}
        for normalized in EC2_STATE_MAP.values():
            assert normalized in valid_states
