# Feature: multi-service-dashboard-iac, Property 7: Idempotent start/stop operations
"""
Property-based tests for idempotent start/stop operations.

**Validates: Requirements 2.11**

Property 7: For any resource already in the "running" normalized state, a start action
SHALL return success without invoking the service API. Similarly, for any resource already
in the "stopped" normalized state, a stop action SHALL return success without invoking the
service API.

Tests all 5 adapters (EC2, RDS, ECS, Lightsail, AppRunner):
- Mock the status check to return "running" state, then call start() → verify no start API was called
- Mock the status check to return "stopped" state, then call stop() → verify no stop API was called
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st


# Strategy: pick a random resource type from all 5 adapters
resource_type_strategy = st.sampled_from(["ec2", "rds", "ecs", "lightsail", "apprunner"])


def _create_ec2_adapter_running():
    """Create an EC2 adapter with a mocked client reporting 'running' state."""
    from ec2_adapter import EC2Adapter

    mock_ec2 = MagicMock()
    mock_ec2.describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": "i-0abc123def456", "State": {"Name": "running"}}]}
        ]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "i-0abc123def456", "type": "ec2"}

    with patch.object(EC2Adapter, "_get_credentials", return_value=None):
        with patch("ec2_adapter.boto3.client", return_value=mock_ec2):
            adapter = EC2Adapter(account, resource)

    return adapter, mock_ec2


def _create_ec2_adapter_stopped():
    """Create an EC2 adapter with a mocked client reporting 'stopped' state."""
    from ec2_adapter import EC2Adapter

    mock_ec2 = MagicMock()
    mock_ec2.describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": "i-0abc123def456", "State": {"Name": "stopped"}}]}
        ]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "i-0abc123def456", "type": "ec2"}

    with patch.object(EC2Adapter, "_get_credentials", return_value=None):
        with patch("ec2_adapter.boto3.client", return_value=mock_ec2):
            adapter = EC2Adapter(account, resource)

    return adapter, mock_ec2


def _create_rds_adapter_running():
    """Create an RDS adapter with a mocked client reporting 'available' (running) state."""
    from rds_adapter import RDSAdapter

    mock_rds = MagicMock()
    mock_rds.describe_db_instances.return_value = {
        "DBInstances": [{"DBInstanceIdentifier": "my-db", "DBInstanceStatus": "available"}]
    }
    mock_rds.describe_db_clusters.return_value = {
        "DBClusters": [{"DBClusterIdentifier": "my-db", "Status": "available"}]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-db", "type": "rds", "resourceType": "instance"}

    with patch.object(RDSAdapter, "_get_credentials", return_value=None):
        with patch("rds_adapter.boto3.client", return_value=mock_rds):
            adapter = RDSAdapter(account, resource)

    return adapter, mock_rds


def _create_rds_adapter_stopped():
    """Create an RDS adapter with a mocked client reporting 'stopped' state."""
    from rds_adapter import RDSAdapter

    mock_rds = MagicMock()
    mock_rds.describe_db_instances.return_value = {
        "DBInstances": [{"DBInstanceIdentifier": "my-db", "DBInstanceStatus": "stopped"}]
    }
    mock_rds.describe_db_clusters.return_value = {
        "DBClusters": [{"DBClusterIdentifier": "my-db", "Status": "stopped"}]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-db", "type": "rds", "resourceType": "instance"}

    with patch.object(RDSAdapter, "_get_credentials", return_value=None):
        with patch("rds_adapter.boto3.client", return_value=mock_rds):
            adapter = RDSAdapter(account, resource)

    return adapter, mock_rds


def _create_ecs_adapter_running():
    """Create an ECS adapter with a mocked client reporting 'running' state."""
    from ecs_adapter import ECSAdapter

    mock_ecs = MagicMock()
    mock_ecs.describe_services.return_value = {
        "services": [
            {
                "serviceName": "my-service",
                "desiredCount": 2,
                "runningCount": 2,
            }
        ]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-cluster/my-service", "type": "ecs", "targetCount": 2}

    with patch.object(ECSAdapter, "_get_credentials", return_value=None):
        with patch("ecs_adapter.boto3.client", return_value=mock_ecs):
            adapter = ECSAdapter(account, resource)

    return adapter, mock_ecs


def _create_ecs_adapter_stopped():
    """Create an ECS adapter with a mocked client reporting 'stopped' state."""
    from ecs_adapter import ECSAdapter

    mock_ecs = MagicMock()
    mock_ecs.describe_services.return_value = {
        "services": [
            {
                "serviceName": "my-service",
                "desiredCount": 0,
                "runningCount": 0,
            }
        ]
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-cluster/my-service", "type": "ecs", "targetCount": 2}

    with patch.object(ECSAdapter, "_get_credentials", return_value=None):
        with patch("ecs_adapter.boto3.client", return_value=mock_ecs):
            adapter = ECSAdapter(account, resource)

    return adapter, mock_ecs


def _create_lightsail_adapter_running():
    """Create a Lightsail adapter with a mocked client reporting 'running' state."""
    from lightsail_adapter import LightsailAdapter

    mock_ls = MagicMock()
    mock_ls.get_instance.return_value = {
        "instance": {"name": "my-instance", "state": {"name": "running"}}
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-instance", "type": "lightsail"}

    with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
        with patch("lightsail_adapter.boto3.client", return_value=mock_ls):
            adapter = LightsailAdapter(account, resource)

    return adapter, mock_ls


def _create_lightsail_adapter_stopped():
    """Create a Lightsail adapter with a mocked client reporting 'stopped' state."""
    from lightsail_adapter import LightsailAdapter

    mock_ls = MagicMock()
    mock_ls.get_instance.return_value = {
        "instance": {"name": "my-instance", "state": {"name": "stopped"}}
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "my-instance", "type": "lightsail"}

    with patch.object(LightsailAdapter, "_get_credentials", return_value=None):
        with patch("lightsail_adapter.boto3.client", return_value=mock_ls):
            adapter = LightsailAdapter(account, resource)

    return adapter, mock_ls


def _create_apprunner_adapter_running():
    """Create an AppRunner adapter with a mocked client reporting 'RUNNING' state."""
    from apprunner_adapter import AppRunnerAdapter

    mock_ar = MagicMock()
    mock_ar.describe_service.return_value = {
        "Service": {"ServiceArn": "arn:aws:apprunner:us-east-1:123:service/my-svc/id", "Status": "RUNNING"}
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "arn:aws:apprunner:us-east-1:123:service/my-svc/id", "type": "apprunner"}

    with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
        with patch("apprunner_adapter.boto3.client", return_value=mock_ar):
            adapter = AppRunnerAdapter(account, resource)

    return adapter, mock_ar


def _create_apprunner_adapter_stopped():
    """Create an AppRunner adapter with a mocked client reporting 'PAUSED' (stopped) state."""
    from apprunner_adapter import AppRunnerAdapter

    mock_ar = MagicMock()
    mock_ar.describe_service.return_value = {
        "Service": {"ServiceArn": "arn:aws:apprunner:us-east-1:123:service/my-svc/id", "Status": "PAUSED"}
    }

    account = {"region": "us-east-1"}
    resource = {"resourceId": "arn:aws:apprunner:us-east-1:123:service/my-svc/id", "type": "apprunner"}

    with patch.object(AppRunnerAdapter, "_get_credentials", return_value=None):
        with patch("apprunner_adapter.boto3.client", return_value=mock_ar):
            adapter = AppRunnerAdapter(account, resource)

    return adapter, mock_ar


# Maps resource type → factory for running adapter
_RUNNING_FACTORIES = {
    "ec2": _create_ec2_adapter_running,
    "rds": _create_rds_adapter_running,
    "ecs": _create_ecs_adapter_running,
    "lightsail": _create_lightsail_adapter_running,
    "apprunner": _create_apprunner_adapter_running,
}

# Maps resource type → factory for stopped adapter
_STOPPED_FACTORIES = {
    "ec2": _create_ec2_adapter_stopped,
    "rds": _create_rds_adapter_stopped,
    "ecs": _create_ecs_adapter_stopped,
    "lightsail": _create_lightsail_adapter_stopped,
    "apprunner": _create_apprunner_adapter_stopped,
}

# Maps resource type → the start API method names that should NOT be called
_START_API_METHODS = {
    "ec2": "start_instances",
    "rds": ["start_db_instance", "start_db_cluster"],
    "ecs": "update_service",
    "lightsail": "start_instance",
    "apprunner": "resume_service",
}

# Maps resource type → the stop API method names that should NOT be called
_STOP_API_METHODS = {
    "ec2": "stop_instances",
    "rds": ["stop_db_instance", "stop_db_cluster"],
    "ecs": "update_service",
    "lightsail": "stop_instance",
    "apprunner": "pause_service",
}


def _assert_start_api_not_called(resource_type: str, mock_client):
    """Assert that no start API method was called on the mock client."""
    methods = _START_API_METHODS[resource_type]
    if isinstance(methods, list):
        for method in methods:
            getattr(mock_client, method).assert_not_called()
    else:
        getattr(mock_client, methods).assert_not_called()


def _assert_stop_api_not_called(resource_type: str, mock_client):
    """Assert that no stop API method was called on the mock client."""
    methods = _STOP_API_METHODS[resource_type]
    if isinstance(methods, list):
        for method in methods:
            getattr(mock_client, method).assert_not_called()
    else:
        getattr(mock_client, methods).assert_not_called()


@settings(max_examples=100)
@given(resource_type=resource_type_strategy)
def test_start_on_running_resource_is_idempotent(resource_type: str):
    """Property: start() on a resource already in 'running' state returns success
    without invoking the service start API.

    For any resource type and any resource already in the "running" normalized state,
    calling start() SHALL return a success response without making the actual start
    API call to the service.
    """
    factory = _RUNNING_FACTORIES[resource_type]
    adapter, mock_client = factory()

    result = adapter.start()

    # Must return success
    if resource_type in ("ec2", "lightsail", "apprunner"):
        assert result.get("status") == "success", (
            f"Expected 'success' status for {resource_type}, got: {result}"
        )
        assert result.get("state") == "running", (
            f"Expected 'running' state for {resource_type}, got: {result}"
        )
    elif resource_type in ("rds", "ecs"):
        assert result.get("state") == "running", (
            f"Expected 'running' state for {resource_type}, got: {result}"
        )

    # Must NOT have called the start API
    _assert_start_api_not_called(resource_type, mock_client)


@settings(max_examples=100)
@given(resource_type=resource_type_strategy)
def test_stop_on_stopped_resource_is_idempotent(resource_type: str):
    """Property: stop() on a resource already in 'stopped' state returns success
    without invoking the service stop API.

    For any resource type and any resource already in the "stopped" normalized state,
    calling stop() SHALL return a success response without making the actual stop
    API call to the service.
    """
    factory = _STOPPED_FACTORIES[resource_type]
    adapter, mock_client = factory()

    result = adapter.stop()

    # Must return success
    if resource_type in ("ec2", "lightsail", "apprunner"):
        assert result.get("status") == "success", (
            f"Expected 'success' status for {resource_type}, got: {result}"
        )
        assert result.get("state") == "stopped", (
            f"Expected 'stopped' state for {resource_type}, got: {result}"
        )
    elif resource_type in ("rds", "ecs"):
        assert result.get("state") == "stopped", (
            f"Expected 'stopped' state for {resource_type}, got: {result}"
        )

    # Must NOT have called the stop API
    _assert_stop_api_not_called(resource_type, mock_client)
