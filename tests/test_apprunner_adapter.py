"""Tests for backend/apprunner_adapter.py - AppRunner Resource Adapter."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestAppRunnerAdapterGetClient:
    """Test _get_client with and without cross-account credentials."""

    @patch("apprunner_adapter.boto3.client")
    def test_direct_client_no_cross_account(self, mock_client):
        from apprunner_adapter import AppRunnerAdapter

        account = {"region": "us-east-1"}
        resource = {"resourceId": "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        mock_client.assert_called_with("apprunner", region_name="us-east-1")

    @patch("apprunner_adapter.boto3.client")
    def test_cross_account_client(self, mock_client):
        from apprunner_adapter import AppRunnerAdapter

        account = {"region": "eu-west-1", "crossAccountRoleArn": "arn:aws:iam::123:role/Test"}
        resource = {"resourceId": "arn:aws:apprunner:eu-west-1:123456789012:service/my-svc/abc123"}
        creds = {
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        }

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=creds):
            adapter = AppRunnerAdapter(account, resource)

        mock_client.assert_called_with(
            "apprunner",
            region_name="eu-west-1",
            aws_access_key_id="AKIA...",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )


class TestAppRunnerAdapterStatus:
    """Test status() method."""

    @patch("apprunner_adapter.boto3.client")
    def test_status_running(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "RUNNING"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert result["rawState"] == "RUNNING"

    @patch("apprunner_adapter.boto3.client")
    def test_status_paused(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "PAUSED"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopped"
        assert result["rawState"] == "PAUSED"

    @patch("apprunner_adapter.boto3.client")
    def test_status_operation_in_progress_pause(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {
                "ServiceArn": service_arn,
                "Status": "OPERATION_IN_PROGRESS",
                "LatestOperation": {"OperationType": "PAUSE_SERVICE"},
            }
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "stopping"

    @patch("apprunner_adapter.boto3.client")
    def test_status_operation_in_progress_resume(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {
                "ServiceArn": service_arn,
                "Status": "OPERATION_IN_PROGRESS",
                "LatestOperation": {"OperationType": "RESUME_SERVICE"},
            }
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "pending"

    @patch("apprunner_adapter.boto3.client")
    def test_status_operation_in_progress_unknown_operation_defaults_pending(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {
                "ServiceArn": service_arn,
                "Status": "OPERATION_IN_PROGRESS",
            }
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "pending"

    @patch("apprunner_adapter.boto3.client")
    def test_status_unknown_state(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "SOME_UNKNOWN_STATE"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "success"
        assert result["state"] == "unknown"

    @patch("apprunner_adapter.boto3.client")
    def test_status_api_error(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "DescribeService",
        )
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.status()
        assert result["status"] == "error"
        assert result["state"] == "unknown"
        assert "apprunner" in result["service"]


class TestAppRunnerAdapterStart:
    """Test start() method with idempotent checks."""

    @patch("apprunner_adapter.boto3.client")
    def test_start_when_paused(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "PAUSED"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "pending"
        mock_apprunner.resume_service.assert_called_once_with(ServiceArn=service_arn)

    @patch("apprunner_adapter.boto3.client")
    def test_start_idempotent_when_already_running(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "RUNNING"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "success"
        assert result["state"] == "running"
        assert "already running" in result["message"]
        mock_apprunner.resume_service.assert_not_called()

    @patch("apprunner_adapter.boto3.client")
    def test_start_api_error(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "PAUSED"}
        }
        mock_apprunner.resume_service.side_effect = ClientError(
            {"Error": {"Code": "InvalidStateException", "Message": "Cannot resume"}},
            "ResumeService",
        )
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.start()
        assert result["status"] == "error"
        assert "apprunner" in result["service"]


class TestAppRunnerAdapterStop:
    """Test stop() method with idempotent checks."""

    @patch("apprunner_adapter.boto3.client")
    def test_stop_when_running(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "RUNNING"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopping"
        mock_apprunner.pause_service.assert_called_once_with(ServiceArn=service_arn)

    @patch("apprunner_adapter.boto3.client")
    def test_stop_idempotent_when_already_paused(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "PAUSED"}
        }
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "success"
        assert result["state"] == "stopped"
        assert "already stopped" in result["message"]
        mock_apprunner.pause_service.assert_not_called()

    @patch("apprunner_adapter.boto3.client")
    def test_stop_api_error(self, mock_boto_client):
        from apprunner_adapter import AppRunnerAdapter

        service_arn = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc/abc123"
        mock_apprunner = MagicMock()
        mock_apprunner.describe_service.return_value = {
            "Service": {"ServiceArn": service_arn, "Status": "RUNNING"}
        }
        mock_apprunner.pause_service.side_effect = ClientError(
            {"Error": {"Code": "InvalidStateException", "Message": "Cannot pause"}},
            "PauseService",
        )
        mock_boto_client.return_value = mock_apprunner

        account = {"region": "us-east-1"}
        resource = {"resourceId": service_arn}

        with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
            adapter = AppRunnerAdapter(account, resource)

        result = adapter.stop()
        assert result["status"] == "error"
        assert "apprunner" in result["service"]


class TestAppRunnerStateMapping:
    """Test AppRunner state to normalized state mapping."""

    def test_state_map_completeness(self):
        from apprunner_adapter import APPRUNNER_STATE_MAP

        assert APPRUNNER_STATE_MAP["RUNNING"] == "running"
        assert APPRUNNER_STATE_MAP["PAUSED"] == "stopped"
        assert APPRUNNER_STATE_MAP["CREATE_FAILED"] == "unknown"
        assert APPRUNNER_STATE_MAP["DELETED"] == "unknown"
        assert APPRUNNER_STATE_MAP["DELETE_FAILED"] == "unknown"

    def test_state_map_values_are_valid_normalized_states(self):
        from apprunner_adapter import APPRUNNER_STATE_MAP

        valid_states = {"running", "stopped", "pending", "stopping", "unknown"}
        for normalized in APPRUNNER_STATE_MAP.values():
            assert normalized in valid_states
