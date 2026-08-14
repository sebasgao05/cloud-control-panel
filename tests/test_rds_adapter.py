"""
Tests for the RDS Resource Adapter.

Validates:
- Correct API dispatch based on resourceType (cluster vs instance)
- State normalization mapping
- Idempotent start/stop behavior
- Error handling with 30-second timeout configuration
- Cross-account credential usage

Requirements: 2.1, 2.2, 2.9, 2.10, 2.11
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from rds_adapter import RDS_BOTO_CONFIG, RDS_STATE_MAP, RDSAdapter


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
def cluster_resource():
    """RDS cluster resource."""
    return {
        "id": "res-rds-1",
        "type": "rds",
        "resourceId": "my-aurora-cluster",
        "resourceType": "cluster",
    }


@pytest.fixture
def instance_resource():
    """RDS instance resource."""
    return {
        "id": "res-rds-2",
        "type": "rds",
        "resourceId": "my-db-instance",
        "resourceType": "instance",
    }


@pytest.fixture
def mock_rds_client():
    """A mock RDS boto3 client."""
    return MagicMock()


# --- Tests for _get_client ---


class TestRDSGetClient:
    """Tests for RDS client creation."""

    @patch("rds_adapter.boto3.client")
    def test_creates_client_with_default_credentials(self, mock_boto_client, account, cluster_resource):
        """Creates RDS client with Lambda default credentials when no role ARN."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)

        mock_boto_client.assert_called_once_with(
            "rds",
            region_name="us-east-1",
            config=RDS_BOTO_CONFIG,
        )
        assert adapter.client == mock_client

    @patch("rds_adapter.boto3.client")
    def test_creates_client_with_cross_account_credentials(self, mock_boto_client, cross_account, cluster_resource):
        """Creates RDS client using STS credentials when role ARN is configured."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA_CROSS",
                "SecretAccessKey": "SECRET_CROSS",
                "SessionToken": "TOKEN_CROSS",
            }
        }
        mock_rds = MagicMock()

        # First call is STS (from _get_credentials), second is RDS
        mock_boto_client.side_effect = [mock_sts, mock_rds]

        adapter = RDSAdapter(cross_account, cluster_resource)

        # Verify STS was called first
        assert mock_boto_client.call_args_list[0] == (
            ("sts",),
            {"region_name": "eu-west-1"},
        )
        # Verify RDS client created with cross-account creds
        assert mock_boto_client.call_args_list[1] == (
            ("rds",),
            {
                "region_name": "eu-west-1",
                "config": RDS_BOTO_CONFIG,
                "aws_access_key_id": "AKIA_CROSS",
                "aws_secret_access_key": "SECRET_CROSS",
                "aws_session_token": "TOKEN_CROSS",
            },
        )

    @patch("rds_adapter.boto3.client")
    def test_timeout_config_is_30_seconds(self, mock_boto_client, account, cluster_resource):
        """Boto3 Config has 30-second connect and read timeout."""
        mock_boto_client.return_value = MagicMock()

        RDSAdapter(account, cluster_resource)

        call_kwargs = mock_boto_client.call_args[1]
        config = call_kwargs["config"]
        assert config.connect_timeout == 30
        assert config.read_timeout == 30


# --- Tests for start() ---


class TestRDSStart:
    """Tests for the RDS start operation."""

    @patch("rds_adapter.boto3.client")
    def test_start_cluster_calls_start_db_cluster(self, mock_boto_client, account, cluster_resource):
        """Start on a cluster resource calls StartDBCluster."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "stopped"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.start()

        mock_client.start_db_cluster.assert_called_once_with(
            DBClusterIdentifier="my-aurora-cluster"
        )
        assert result["state"] == "pending"
        assert result["resourceId"] == "my-aurora-cluster"

    @patch("rds_adapter.boto3.client")
    def test_start_instance_calls_start_db_instance(self, mock_boto_client, account, instance_resource):
        """Start on an instance resource calls StartDBInstance."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.start()

        mock_client.start_db_instance.assert_called_once_with(
            DBInstanceIdentifier="my-db-instance"
        )
        assert result["state"] == "pending"
        assert result["resourceId"] == "my-db-instance"

    @patch("rds_adapter.boto3.client")
    def test_start_idempotent_when_already_running(self, mock_boto_client, account, cluster_resource):
        """Start returns success without API call when already running."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "available"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.start()

        mock_client.start_db_cluster.assert_not_called()
        assert result["state"] == "running"
        assert "already" in result["message"].lower()

    @patch("rds_adapter.boto3.client")
    def test_start_handles_client_error(self, mock_boto_client, account, instance_resource):
        """Start returns error dict on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }
        mock_client.start_db_instance.side_effect = ClientError(
            {"Error": {"Code": "InvalidDBInstanceState", "Message": "Cannot start"}},
            "StartDBInstance",
        )
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.start()

        assert result["state"] == "error"
        assert result["error"] is True
        assert "InvalidDBInstanceState" in result["message"]
        assert "my-db-instance" in result["message"]


# --- Tests for stop() ---


class TestRDSStop:
    """Tests for the RDS stop operation."""

    @patch("rds_adapter.boto3.client")
    def test_stop_cluster_calls_stop_db_cluster(self, mock_boto_client, account, cluster_resource):
        """Stop on a cluster resource calls StopDBCluster."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "available"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.stop()

        mock_client.stop_db_cluster.assert_called_once_with(
            DBClusterIdentifier="my-aurora-cluster"
        )
        assert result["state"] == "stopping"
        assert result["resourceId"] == "my-aurora-cluster"

    @patch("rds_adapter.boto3.client")
    def test_stop_instance_calls_stop_db_instance(self, mock_boto_client, account, instance_resource):
        """Stop on an instance resource calls StopDBInstance."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.stop()

        mock_client.stop_db_instance.assert_called_once_with(
            DBInstanceIdentifier="my-db-instance"
        )
        assert result["state"] == "stopping"
        assert result["resourceId"] == "my-db-instance"

    @patch("rds_adapter.boto3.client")
    def test_stop_idempotent_when_already_stopped(self, mock_boto_client, account, instance_resource):
        """Stop returns success without API call when already stopped."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.stop()

        mock_client.stop_db_instance.assert_not_called()
        assert result["state"] == "stopped"
        assert "already" in result["message"].lower()

    @patch("rds_adapter.boto3.client")
    def test_stop_handles_client_error(self, mock_boto_client, account, cluster_resource):
        """Stop returns error dict on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "available"}]
        }
        mock_client.stop_db_cluster.side_effect = ClientError(
            {"Error": {"Code": "InvalidDBClusterStateFault", "Message": "Cannot stop"}},
            "StopDBCluster",
        )
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.stop()

        assert result["state"] == "error"
        assert result["error"] is True
        assert "InvalidDBClusterStateFault" in result["message"]


# --- Tests for status() ---


class TestRDSStatus:
    """Tests for the RDS status operation."""

    @patch("rds_adapter.boto3.client")
    def test_status_cluster_reads_db_cluster_status(self, mock_boto_client, account, cluster_resource):
        """Status for cluster calls describe_db_clusters."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "available"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.status()

        mock_client.describe_db_clusters.assert_called_with(
            DBClusterIdentifier="my-aurora-cluster"
        )
        assert result["state"] == "running"
        assert result["rawState"] == "available"

    @patch("rds_adapter.boto3.client")
    def test_status_instance_reads_db_instance_status(self, mock_boto_client, account, instance_resource):
        """Status for instance calls describe_db_instances."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.status()

        mock_client.describe_db_instances.assert_called_with(
            DBInstanceIdentifier="my-db-instance"
        )
        assert result["state"] == "stopped"
        assert result["rawState"] == "stopped"

    @patch("rds_adapter.boto3.client")
    @pytest.mark.parametrize(
        "raw_state,expected_normalized",
        [
            ("available", "running"),
            ("stopped", "stopped"),
            ("starting", "pending"),
            ("creating", "pending"),
            ("stopping", "stopping"),
            ("deleting", "unknown"),
            ("rebooting", "unknown"),
            ("modifying", "unknown"),
        ],
    )
    def test_state_normalization_map(
        self, mock_boto_client, account, instance_resource, raw_state, expected_normalized
    ):
        """Each RDS state maps to the correct normalized state."""
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": raw_state}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, instance_resource)
        result = adapter.status()

        assert result["state"] == expected_normalized

    @patch("rds_adapter.boto3.client")
    def test_status_handles_client_error(self, mock_boto_client, account, cluster_resource):
        """Status returns unknown state on ClientError."""
        mock_client = MagicMock()
        mock_client.describe_db_clusters.side_effect = ClientError(
            {"Error": {"Code": "DBClusterNotFoundFault", "Message": "Not found"}},
            "DescribeDBClusters",
        )
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, cluster_resource)
        result = adapter.status()

        assert result["state"] == "unknown"
        assert result["rawState"] == "error"
        assert result["error"] is True


# --- Tests for resourceType default behavior ---


class TestRDSResourceTypeDefault:
    """Tests for default resourceType handling."""

    @patch("rds_adapter.boto3.client")
    def test_defaults_to_instance_when_resource_type_missing(self, mock_boto_client, account):
        """When resourceType is not specified, defaults to instance."""
        resource = {
            "id": "res-rds-3",
            "type": "rds",
            "resourceId": "default-db",
        }
        mock_client = MagicMock()
        mock_client.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }
        mock_boto_client.return_value = mock_client

        adapter = RDSAdapter(account, resource)
        result = adapter.start()

        mock_client.start_db_instance.assert_called_once_with(
            DBInstanceIdentifier="default-db"
        )


# --- Tests for state map constant ---


class TestRDSStateMap:
    """Tests for the RDS_STATE_MAP constant."""

    def test_state_map_contains_required_states(self):
        """RDS_STATE_MAP has all required state mappings."""
        assert RDS_STATE_MAP["available"] == "running"
        assert RDS_STATE_MAP["stopped"] == "stopped"
        assert RDS_STATE_MAP["starting"] == "pending"
        assert RDS_STATE_MAP["creating"] == "pending"
        assert RDS_STATE_MAP["stopping"] == "stopping"

    def test_state_map_unknown_for_unmapped_states(self):
        """Unmapped states return 'unknown' via dict.get."""
        assert RDS_STATE_MAP.get("deleting", "unknown") == "unknown"
        assert RDS_STATE_MAP.get("rebooting", "unknown") == "unknown"
        assert RDS_STATE_MAP.get("some-random-state", "unknown") == "unknown"
