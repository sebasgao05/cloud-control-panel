# Feature: multi-service-dashboard-iac, Property 5: ECS start uses configured targetCount
"""
Property-based tests for ECS adapter start using configured targetCount.

**Validates: Requirements 2.3**

Property 5: For any ECS resource with a `targetCount` value between 1 and 10,
the ECS adapter start action SHALL call UpdateService with `desiredCount` equal
to that `targetCount` value.
"""

import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from ecs_adapter import ECSAdapter


@settings(max_examples=100)
@given(target_count=st.integers(min_value=1, max_value=10))
def test_ecs_start_calls_update_service_with_configured_target_count(target_count: int):
    """Property: ECS adapter start always calls UpdateService with desiredCount
    equal to the resource's targetCount (1-10).

    For any targetCount in [1, 10], when the ECS adapter start method is invoked
    on a stopped service, UpdateService must be called with desiredCount matching
    that targetCount value exactly.
    """
    account = {"id": "test-account", "region": "us-east-1"}
    resource = {
        "id": "ecs-resource",
        "type": "ecs",
        "resourceId": "my-cluster/my-service",
        "targetCount": target_count,
    }

    with patch("ecs_adapter.boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        # Simulate service is currently stopped so start will proceed
        mock_client.describe_services.return_value = {
            "services": [{"desiredCount": 0, "runningCount": 0}]
        }
        mock_boto_client.return_value = mock_client

        adapter = ECSAdapter(account, resource)
        result = adapter.start()

        # Verify UpdateService was called with the exact targetCount
        mock_client.update_service.assert_called_once_with(
            cluster="my-cluster",
            service="my-service",
            desiredCount=target_count,
        )

        # The result should indicate the service is starting
        assert result["state"] == "pending"
        assert result["resourceId"] == "my-cluster/my-service"
