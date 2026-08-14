# Feature: multi-service-dashboard-iac, Property 4: RDS adapter dispatches correct API based on action and resourceType
"""
Property-based tests for RDS adapter API dispatch.

**Validates: Requirements 2.1, 2.2**

Property 4: For any RDS resource with `resourceType` in ["cluster", "instance"] and
any action in ["start", "stop"], the RDS adapter SHALL invoke:
- `StartDBCluster`/`StopDBCluster` when resourceType is "cluster"
- `StartDBInstance`/`StopDBInstance` when resourceType is "instance"
"""

import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from rds_adapter import RDSAdapter


# Strategies for the two dimensions
resource_types = st.sampled_from(["cluster", "instance"])
actions = st.sampled_from(["start", "stop"])

# Strategy for valid RDS resource identifiers (1-63 alphanumeric + hyphens)
rds_resource_ids = st.from_regex(r"[a-z][a-z0-9\-]{0,62}", fullmatch=True).filter(
    lambda s: len(s) >= 1 and len(s) <= 63
)


def _make_rds_resource(resource_type: str, resource_id: str) -> dict:
    """Build an RDS resource dict for the given resourceType."""
    return {
        "id": "test-rds",
        "type": "rds",
        "resourceId": resource_id,
        "resourceType": resource_type,
    }


def _make_account() -> dict:
    """Build a minimal account dict."""
    return {"id": "acc-test", "region": "us-east-1"}


def _mock_status_response(resource_type: str, state: str) -> dict:
    """Build the boto3 response for a describe call returning the given state."""
    if resource_type == "cluster":
        return {"DBClusters": [{"Status": state}]}
    else:
        return {"DBInstances": [{"DBInstanceStatus": state}]}


# Expected method names for each combination
EXPECTED_DISPATCH = {
    ("cluster", "start"): "start_db_cluster",
    ("cluster", "stop"): "stop_db_cluster",
    ("instance", "start"): "start_db_instance",
    ("instance", "stop"): "stop_db_instance",
}

# The status methods that should be called for idempotent check
STATUS_METHODS = {
    "cluster": "describe_db_clusters",
    "instance": "describe_db_instances",
}

# State that does NOT match the action target (so the action API will be invoked)
NON_TARGET_STATE = {
    "start": "stopped",  # resource is stopped, so start will call the API
    "stop": "available",  # resource is available/running, so stop will call the API
}


@settings(max_examples=100)
@given(
    resource_type=resource_types,
    action=actions,
    resource_id=rds_resource_ids,
)
@patch("rds_adapter.boto3.client")
def test_rds_dispatches_correct_api_for_action_and_resource_type(
    mock_boto_client: MagicMock,
    resource_type: str,
    action: str,
    resource_id: str,
):
    """Property: For any (resourceType, action) combination, the RDS adapter invokes
    the correct boto3 method: StartDBCluster/StopDBCluster for clusters,
    StartDBInstance/StopDBInstance for instances."""
    # Setup mock client
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    # Configure status response so the idempotent check does NOT short-circuit
    # (resource is in a state where the action will proceed)
    state_for_describe = NON_TARGET_STATE[action]
    status_method_name = STATUS_METHODS[resource_type]
    getattr(mock_client, status_method_name).return_value = _mock_status_response(
        resource_type, state_for_describe
    )

    # Create adapter and invoke the action
    account = _make_account()
    resource = _make_rds_resource(resource_type, resource_id)
    adapter = RDSAdapter(account, resource)

    # Call the action method
    getattr(adapter, action)()

    # Verify the correct boto3 method was called
    expected_method = EXPECTED_DISPATCH[(resource_type, action)]
    called_method = getattr(mock_client, expected_method)
    called_method.assert_called_once()

    # Verify the correct identifier parameter was passed
    call_kwargs = called_method.call_args[1]
    if resource_type == "cluster":
        assert call_kwargs["DBClusterIdentifier"] == resource_id
    else:
        assert call_kwargs["DBInstanceIdentifier"] == resource_id

    # Verify the OTHER methods were NOT called (only the expected one was invoked)
    other_methods = [
        m for key, m in EXPECTED_DISPATCH.items() if key != (resource_type, action)
    ]
    for other_method in other_methods:
        getattr(mock_client, other_method).assert_not_called()
