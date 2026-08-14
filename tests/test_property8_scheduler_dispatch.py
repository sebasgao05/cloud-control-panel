# Feature: multi-service-dashboard-iac, Property 8: Scheduler dispatches to correct adapter by resource type
"""
Property-based tests for scheduler adapter dispatch.

**Validates: Requirements 4.1, 4.2**

Property 8: For any scheduled event targeting a resource of a supported type,
the scheduler SHALL invoke the adapter corresponding to that resource's type field
(not the EC2 adapter by default).
"""

import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from scheduler import handle_scheduler_event


# Strategies
resource_types = st.sampled_from(["ec2", "rds", "ecs", "lightsail", "apprunner"])
actions = st.sampled_from(["start", "stop"])


def _make_resource(resource_type: str, resource_id: str = "res-1") -> dict:
    """Build a resource dict with the given type."""
    return {
        "id": resource_id,
        "name": f"Test {resource_type} resource",
        "type": resource_type,
        "resourceId": "i-abc123def456" if resource_type == "ec2" else "some-resource-id",
    }


def _make_account(account_id: str, resources: list) -> dict:
    """Build an account dict containing the specified resources."""
    return {
        "id": account_id,
        "region": "us-east-1",
        "resources": resources,
        "instances": [],
    }


@settings(max_examples=100)
@given(
    resource_type=resource_types,
    action=actions,
)
@patch("scheduler.send_notifications")
@patch("scheduler.log_activity")
@patch("scheduler.load_config_from_db")
@patch("resource_adapter.get_adapter")
def test_scheduler_dispatches_to_correct_adapter_by_resource_type(
    mock_get_adapter: MagicMock,
    mock_load_config: MagicMock,
    mock_log_activity: MagicMock,
    mock_send_notifications: MagicMock,
    resource_type: str,
    action: str,
):
    """Property: For any scheduled event targeting a resource of a supported type,
    the scheduler invokes the adapter matching that resource's type field."""
    # Arrange
    resource_id = "res-test-1"
    account_id = "acc-test"

    resource = _make_resource(resource_type, resource_id)
    account = _make_account(account_id, [resource])

    # Mock load_config_from_db to return config with our account
    mock_load_config.return_value = {"accounts": [account]}

    # Mock get_adapter to return a mock adapter
    mock_adapter = MagicMock()
    mock_get_adapter.return_value = mock_adapter

    # Build a multi-service event payload (uses resourceIds)
    event = {
        "action": action,
        "accountId": account_id,
        "resourceIds": [resource_id],
        "ruleId": "rule-123",
    }

    # Act
    result = handle_scheduler_event(event)

    # Assert: get_adapter was called with the account and the resource that has the correct type
    mock_get_adapter.assert_called_once_with(account, resource)

    # Assert: the adapter's correct method (start or stop) was called
    if action == "start":
        mock_adapter.start.assert_called_once()
        mock_adapter.stop.assert_not_called()
    else:
        mock_adapter.stop.assert_called_once()
        mock_adapter.start.assert_not_called()

    # Assert: successful response
    assert result["statusCode"] == 200


@settings(max_examples=100)
@given(
    resource_type=resource_types,
    action=actions,
)
@patch("scheduler.send_notifications")
@patch("scheduler.log_activity")
@patch("scheduler.load_config_from_db")
@patch("resource_adapter.get_adapter")
def test_scheduler_does_not_default_to_ec2_adapter(
    mock_get_adapter: MagicMock,
    mock_load_config: MagicMock,
    mock_log_activity: MagicMock,
    mock_send_notifications: MagicMock,
    resource_type: str,
    action: str,
):
    """Property: The scheduler passes the exact resource (with its type) to get_adapter,
    ensuring the factory dispatches to the correct adapter class rather than defaulting to EC2."""
    resource_id = "res-verify"
    account_id = "acc-verify"

    resource = _make_resource(resource_type, resource_id)
    account = _make_account(account_id, [resource])

    mock_load_config.return_value = {"accounts": [account]}

    mock_adapter = MagicMock()
    mock_get_adapter.return_value = mock_adapter

    event = {
        "action": action,
        "accountId": account_id,
        "resourceIds": [resource_id],
        "ruleId": "rule-456",
    }

    handle_scheduler_event(event)

    # Verify get_adapter received the resource with the correct type field
    call_args = mock_get_adapter.call_args
    passed_resource = call_args[0][1]  # second positional argument
    assert passed_resource["type"] == resource_type
    assert passed_resource["id"] == resource_id
