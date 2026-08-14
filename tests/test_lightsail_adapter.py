"""Tests for backend/lightsail_adapter.py - Lightsail Resource Adapter."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestLightsailAdapterGetClient:
    """Test _get_client with and without cross-account credentials."""

    @patch("lightsail_adapter.boto3.client")
    def test_direct_client_no_cross_account(self, mock_client):
        from lightsail_adapter import LightsailAdapter

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-lightsail-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        mock_client.assert_called_with("lightsail", region_name="us-east-1")

    @patch("lightsail_adapter.boto3.client")
    def test_cross_account_client(self, mock_client):
        from lightsail_adapter import LightsailAdapter

        account = {"region": "eu-west-1", "crossAccountRoleArn": "arn:aws:iam::123:role/Test"}
        resource = {"resourceId": "my-lightsail-instance"}
        creds = {
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        }

        with patch.object(LightsailAdapter, "_get_credentials", return_value=creds):
            adapter = LightsailAdapter(account, resource)

        mock_client.assert_called_with(
            "lightsail",
            region_name="eu-west-1",
            aws_access_key_id="AKIA...",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )


class TestLightsailAdapterStatus:
    """Test status() method."""

    @patch("lightsail_adapter.boto3.client")
    def test_status_running(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "running"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert result["rawState"] == "running"

    @patch("lightsail_adapter.boto3.client")
    def test_status_stopped(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "stopped"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopped"

    @patch("lightsail_adapter.boto3.client")
    def test_status_pending(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "pending"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "pending"

    @patch("lightsail_adapter.boto3.client")
    def test_status_stopping(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "stopping"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopping"

    @patch("lightsail_adapter.boto3.client")
    def test_status_unknown_state(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "some-other-state"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "unknown"

    @patch("lightsail_adapter.boto3.client")
    def test_status_api_error(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.side_effect = ClientError(
            {"Error": {"Code": "NotFoundException", "Message": "Not found"}},
            "GetInstance",
        )
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "error"
        assert result["state"] == "unknown"
        assert result["service"] == "lightsail"


class TestLightsailAdapterStart:
    """Test start() method with idempotent checks."""

    @patch("lightsail_adapter.boto3.client")
    def test_start_when_stopped(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "stopped"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "pending"
        mock_ls.start_instance.assert_called_once_with(instanceName="my-instance")

    @patch("lightsail_adapter.boto3.client")
    def test_start_idempotent_when_already_running(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "running"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert "already running" in result["message"]
        mock_ls.start_instance.assert_not_called()

    @patch("lightsail_adapter.boto3.client")
    def test_start_api_error(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "stopped"}}
        }
        mock_ls.start_instance.side_effect = ClientError(
            {"Error": {"Code": "InvalidInputException", "Message": "Cannot start"}},
            "StartInstance",
        )
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "error"
        assert result["service"] == "lightsail"


class TestLightsailAdapterStop:
    """Test stop() method with idempotent checks."""

    @patch("lightsail_adapter.boto3.client")
    def test_stop_when_running(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "running"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopping"
        mock_ls.stop_instance.assert_called_once_with(instanceName="my-instance")

    @patch("lightsail_adapter.boto3.client")
    def test_stop_idempotent_when_already_stopped(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "stopped"}}
        }
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopped"
        assert "already stopped" in result["message"]
        mock_ls.stop_instance.assert_not_called()

    @patch("lightsail_adapter.boto3.client")
    def test_stop_api_error(self, mock_boto_client):
        from lightsail_adapter import LightsailAdapter

        mock_ls = MagicMock()
        mock_ls.get_instance.return_value = {
            "instance": {"name": "my-instance", "state": {"name": "running"}}
        }
        mock_ls.stop_instance.side_effect = ClientError(
            {"Error": {"Code": "InvalidInputException", "Message": "Cannot stop"}},
            "StopInstance",
        )
        mock_boto_client.return_value = mock_ls

        account = {"region": "us-east-1"}
        resource = {"resourceId": "my-instance"}

        with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
            adapter = LightsailAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "error"
        assert result["service"] == "lightsail"


class TestLightsailStateMapping:
    """Test Lightsail state to normalized state mapping."""

    def test_state_map_completeness(self):
        from lightsail_adapter import LIGHTSAIL_STATE_MAP

        assert LIGHTSAIL_STATE_MAP["running"] == "running"
        assert LIGHTSAIL_STATE_MAP["stopped"] == "stopped"
        assert LIGHTSAIL_STATE_MAP["pending"] == "pending"
        assert LIGHTSAIL_STATE_MAP["stopping"] == "stopping"

    def test_state_map_values_are_valid_normalized_states(self):
        from lightsail_adapter import LIGHTSAIL_STATE_MAP

        valid_states = {"running", "stopped", "pending", "stopping", "unknown"}
        for normalized in LIGHTSAIL_STATE_MAP.values():
            assert normalized in valid_states
