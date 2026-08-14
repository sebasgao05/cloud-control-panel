# Feature: multi-service-dashboard-iac, Property 14: Metrics CPU values are within valid percentage range
"""
Property-based tests for metrics CPU utilization value range.

**Validates: Requirements 10.2**

Property 14: For any CloudWatch data point returned by the metrics endpoint
for CPU utilization, the value SHALL be a number in the range [0, 100]
representing a percentage.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from metrics import handle_get_metrics


# Strategy: generate a list of CloudWatch-style datapoints with valid CPU percentages [0, 100]
valid_cpu_values = st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)

# Strategy: generate a list of datapoints (1 to 12 data points for a 60-min window at 5-min intervals)
valid_datapoints_list = st.lists(valid_cpu_values, min_size=1, max_size=12)

# Strategy for resource types that support CPU metrics
resource_types = st.sampled_from(["ec2", "rds", "ecs", "lightsail", "apprunner"])


@settings(max_examples=100)
@given(cpu_values=valid_datapoints_list, resource_type=resource_types)
def test_cpu_values_within_valid_percentage_range(cpu_values: list, resource_type: str):
    """Property: All CPU data points returned by handle_get_metrics are numbers in [0, 100].

    For any set of CloudWatch data points with Average values in [0, 100],
    the metrics endpoint SHALL return CPU values that are numbers within [0, 100].
    """
    now = datetime.now(timezone.utc)

    # Build mock CloudWatch datapoints
    mock_datapoints = [
        {"Timestamp": now - timedelta(minutes=5 * i), "Average": val}
        for i, val in enumerate(cpu_values)
    ]

    # Build resource config based on type
    resource_id_map = {
        "ec2": "i-0abc123def456",
        "rds": "my-db-instance",
        "ecs": "prod-cluster/web-service",
        "lightsail": "my-lightsail-instance",
        "apprunner": "arn:aws:apprunner:us-east-1:123456789:service/my-svc/abc123",
    }

    account = {"id": "test-account", "region": "us-east-1"}
    resource = {
        "id": "test-resource",
        "type": resource_type,
        "resourceId": resource_id_map[resource_type],
        "state": "running",
    }

    with patch("metrics.boto3.client") as mock_boto_client:
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        # For types that support memory (ec2, ecs), we need two responses
        supports_memory = resource_type in ("ec2", "ecs")
        if supports_memory:
            mock_cw.get_metric_statistics.side_effect = [
                {"Datapoints": mock_datapoints},  # CPU response
                {"Datapoints": []},  # Memory response (empty)
            ]
        else:
            mock_cw.get_metric_statistics.return_value = {
                "Datapoints": mock_datapoints
            }

        result = handle_get_metrics(account, resource)

    # Verify no error occurred
    assert "error" not in result, f"Unexpected error: {result.get('error')}"

    # Property assertion: all CPU values must be numbers in [0, 100]
    assert len(result["cpu"]) == len(cpu_values)
    for datapoint in result["cpu"]:
        value = datapoint["value"]
        assert isinstance(value, (int, float)), f"CPU value must be a number, got {type(value)}"
        assert 0 <= value <= 100, f"CPU value {value} is outside valid range [0, 100]"


@settings(max_examples=100)
@given(
    cpu_values=st.lists(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    )
)
def test_cpu_values_are_rounded_and_still_in_range(cpu_values: list):
    """Property: After rounding, CPU values remain within [0, 100].

    The metrics endpoint rounds values to 2 decimal places. This test verifies
    that rounding never pushes a valid value outside the [0, 100] range.
    """
    now = datetime.now(timezone.utc)

    mock_datapoints = [
        {"Timestamp": now - timedelta(minutes=5 * i), "Average": val}
        for i, val in enumerate(cpu_values)
    ]

    account = {"id": "test-account", "region": "us-east-1"}
    resource = {
        "id": "test-resource",
        "type": "ec2",
        "resourceId": "i-0abc123def456",
        "state": "running",
    }

    with patch("metrics.boto3.client") as mock_boto_client:
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        mock_cw.get_metric_statistics.side_effect = [
            {"Datapoints": mock_datapoints},  # CPU
            {"Datapoints": []},  # Memory
        ]

        result = handle_get_metrics(account, resource)

    assert "error" not in result
    for datapoint in result["cpu"]:
        value = datapoint["value"]
        assert isinstance(value, (int, float))
        assert 0 <= value <= 100, f"Rounded CPU value {value} outside [0, 100]"
        # Verify rounding to 2 decimal places
        assert value == round(value, 2), f"CPU value {value} not rounded to 2 decimals"
