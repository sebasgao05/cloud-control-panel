"""
Tests for the ResourceAdapter base class and get_adapter() factory.

Validates:
- Cross-account STS AssumeRole logic with proper session name and duration
- Distinct handling of AccessDenied and ExpiredToken errors
- Factory dispatching by resource type
- Factory rejection of unsupported resource types
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from resource_adapter import NormalizedState, ResourceAdapter, get_adapter


# --- Concrete test adapter for testing the base class ---


class ConcreteAdapter(ResourceAdapter):
    """Minimal concrete adapter for testing base class behavior."""

    def _get_client(self):
        return MagicMock()

    def start(self) -> dict:
        return {"state": "running"}

    def stop(self) -> dict:
        return {"state": "stopped"}

    def status(self) -> dict:
        return {"state": "running"}


# --- Tests for _get_credentials ---


class TestGetCredentials:
    """Tests for the _get_credentials method."""

    def test_returns_none_when_no_role_arn(self):
        """When no crossAccountRoleArn is configured, returns None."""
        account = {"id": "acc-1", "region": "us-east-1"}
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        result = adapter._get_credentials()
        assert result is None

    def test_returns_none_when_role_arn_is_none(self):
        """When crossAccountRoleArn is explicitly None, returns None."""
        account = {"id": "acc-1", "region": "us-east-1", "crossAccountRoleArn": None}
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        result = adapter._get_credentials()
        assert result is None

    @patch("resource_adapter.boto3.client")
    def test_calls_sts_with_correct_params(self, mock_boto_client):
        """STS AssumeRole is called with session name and 3600s duration."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA_TEST",
                "SecretAccessKey": "SECRET_TEST",
                "SessionToken": "TOKEN_TEST",
            }
        }
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "region": "eu-west-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/TestRole",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        result = adapter._get_credentials()

        mock_boto_client.assert_called_with("sts", region_name="eu-west-1")
        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::123456789012:role/TestRole",
            RoleSessionName="CloudControlPanel",
            DurationSeconds=3600,
        )
        assert result == {
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "SECRET_TEST",
            "aws_session_token": "TOKEN_TEST",
        }

    @patch("resource_adapter.boto3.client")
    def test_uses_default_region_when_not_specified(self, mock_boto_client):
        """Uses us-east-1 when account has no region field."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "ST",
            }
        }
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/R",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        adapter._get_credentials()

        mock_boto_client.assert_called_with("sts", region_name="us-east-1")

    @patch("resource_adapter.boto3.client")
    def test_raises_permission_error_on_access_denied(self, mock_boto_client):
        """AccessDenied error raises PermissionError."""
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "AssumeRole",
        )
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/R",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        with pytest.raises(PermissionError, match="Cross-account access denied for account acc-1"):
            adapter._get_credentials()

    @patch("resource_adapter.boto3.client")
    def test_raises_runtime_error_on_expired_token(self, mock_boto_client):
        """ExpiredToken error raises RuntimeError."""
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "ExpiredTokenException", "Message": "Token expired"}},
            "AssumeRole",
        )
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/R",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        with pytest.raises(RuntimeError, match="Cross-account session expired for account acc-1"):
            adapter._get_credentials()

    @patch("resource_adapter.boto3.client")
    def test_raises_runtime_error_on_expired_token_variant(self, mock_boto_client):
        """ExpiredToken (without Exception suffix) also raises RuntimeError."""
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "ExpiredToken", "Message": "Token expired"}},
            "AssumeRole",
        )
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/R",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        with pytest.raises(RuntimeError, match="Cross-account session expired for account acc-1"):
            adapter._get_credentials()

    @patch("resource_adapter.boto3.client")
    def test_raises_generic_exception_on_other_errors(self, mock_boto_client):
        """Other AWS errors raise a generic Exception with error code."""
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "MalformedPolicyDocument", "Message": "Bad policy"}},
            "AssumeRole",
        )
        mock_boto_client.return_value = mock_sts

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/R",
        }
        resource = {"id": "res-1", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        with pytest.raises(Exception, match="Cross-account access failed for account acc-1: MalformedPolicyDocument"):
            adapter._get_credentials()


# --- Tests for get_adapter factory ---


class TestGetAdapterFactory:
    """Tests for the get_adapter() factory function."""

    @patch("resource_adapter.EC2Adapter", create=True)
    def test_dispatches_ec2(self, _mock):
        """Factory creates EC2Adapter for type 'ec2'."""
        with patch("resource_adapter.EC2Adapter", create=True) as MockAdapter:
            # Patch at the import level within the function
            with patch.dict("sys.modules", {"ec2_adapter": MagicMock(EC2Adapter=MockAdapter)}):
                account = {"id": "a", "region": "us-east-1"}
                resource = {"id": "r", "type": "ec2"}
                result = get_adapter(account, resource)
                MockAdapter.assert_called_once_with(account, resource)

    def test_raises_for_unsupported_type(self):
        """Factory raises ValueError for unsupported resource types."""
        account = {"id": "a", "region": "us-east-1"}
        resource = {"id": "r", "type": "lambda"}

        with pytest.raises(ValueError, match="Unsupported resource type: lambda"):
            get_adapter(account, resource)

    def test_raises_for_empty_type(self):
        """Factory raises ValueError when type is an unrecognized string."""
        account = {"id": "a", "region": "us-east-1"}
        resource = {"id": "r", "type": "invalid-service"}

        with pytest.raises(ValueError, match="Unsupported resource type: invalid-service"):
            get_adapter(account, resource)

    def test_defaults_to_ec2_when_type_missing(self):
        """Factory defaults to ec2 when no type field is present."""
        with patch.dict("sys.modules", {"ec2_adapter": MagicMock()}):
            import sys
            mock_module = sys.modules["ec2_adapter"]
            mock_adapter_instance = MagicMock()
            mock_module.EC2Adapter.return_value = mock_adapter_instance

            account = {"id": "a", "region": "us-east-1"}
            resource = {"id": "r"}  # no type field

            result = get_adapter(account, resource)
            mock_module.EC2Adapter.assert_called_once_with(account, resource)

    def test_dispatches_rds(self):
        """Factory creates RDSAdapter for type 'rds'."""
        with patch.dict("sys.modules", {"rds_adapter": MagicMock()}):
            import sys
            mock_module = sys.modules["rds_adapter"]
            mock_adapter_instance = MagicMock()
            mock_module.RDSAdapter.return_value = mock_adapter_instance

            account = {"id": "a", "region": "us-east-1"}
            resource = {"id": "r", "type": "rds"}

            result = get_adapter(account, resource)
            mock_module.RDSAdapter.assert_called_once_with(account, resource)

    def test_dispatches_ecs(self):
        """Factory creates ECSAdapter for type 'ecs'."""
        with patch.dict("sys.modules", {"ecs_adapter": MagicMock()}):
            import sys
            mock_module = sys.modules["ecs_adapter"]
            mock_adapter_instance = MagicMock()
            mock_module.ECSAdapter.return_value = mock_adapter_instance

            account = {"id": "a", "region": "us-east-1"}
            resource = {"id": "r", "type": "ecs"}

            result = get_adapter(account, resource)
            mock_module.ECSAdapter.assert_called_once_with(account, resource)

    def test_dispatches_lightsail(self):
        """Factory creates LightsailAdapter for type 'lightsail'."""
        with patch.dict("sys.modules", {"lightsail_adapter": MagicMock()}):
            import sys
            mock_module = sys.modules["lightsail_adapter"]
            mock_adapter_instance = MagicMock()
            mock_module.LightsailAdapter.return_value = mock_adapter_instance

            account = {"id": "a", "region": "us-east-1"}
            resource = {"id": "r", "type": "lightsail"}

            result = get_adapter(account, resource)
            mock_module.LightsailAdapter.assert_called_once_with(account, resource)

    def test_dispatches_apprunner(self):
        """Factory creates AppRunnerAdapter for type 'apprunner'."""
        with patch.dict("sys.modules", {"apprunner_adapter": MagicMock()}):
            import sys
            mock_module = sys.modules["apprunner_adapter"]
            mock_adapter_instance = MagicMock()
            mock_module.AppRunnerAdapter.return_value = mock_adapter_instance

            account = {"id": "a", "region": "us-east-1"}
            resource = {"id": "r", "type": "apprunner"}

            result = get_adapter(account, resource)
            mock_module.AppRunnerAdapter.assert_called_once_with(account, resource)


# --- Tests for abstract interface ---


class TestResourceAdapterInterface:
    """Tests for the abstract interface contract."""

    def test_cannot_instantiate_abstract_class(self):
        """ResourceAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ResourceAdapter({"id": "a"}, {"id": "r"})

    def test_concrete_adapter_initializes_client(self):
        """Concrete adapter calls _get_client during __init__."""
        account = {"id": "a", "region": "us-east-1"}
        resource = {"id": "r", "type": "ec2"}
        adapter = ConcreteAdapter(account, resource)

        assert adapter.client is not None
        assert adapter.account == account
        assert adapter.resource == resource
