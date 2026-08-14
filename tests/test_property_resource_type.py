# Feature: multi-service-dashboard-iac, Property 1: Resource type validation
"""
Property-based tests for resource type validation.

**Validates: Requirements 1.1, 1.3**

Property 1: For any string value submitted as a resource `type` field, the validation
function SHALL accept it if and only if it is one of the five allowed values:
"ec2", "rds", "ecs", "lightsail", "apprunner". All other strings SHALL be rejected
with an error.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from validators import CreateResourceRequest, RESOURCE_TYPES


# The five allowed resource type values
VALID_TYPES = list(RESOURCE_TYPES)  # ("ec2", "rds", "ecs", "lightsail", "apprunner")


def _make_valid_payload(resource_type: str) -> dict:
    """Build a minimal valid resource creation payload for the given type.

    Uses a compliant resourceId for each type so that only the `type` field
    is the variable under test.
    """
    resource_ids = {
        "ec2": "i-0abcdef1234567890",
        "rds": "my-rds-cluster-1",
        "ecs": "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service",
        "lightsail": "my-lightsail-instance",
        "apprunner": "arn:aws:apprunner:us-east-1:123456789012:service/my-service/id",
    }
    return {
        "id": "test-resource",
        "name": "Test Resource",
        "type": resource_type,
        "resourceId": resource_ids.get(resource_type, "i-0abcdef1234567890"),
    }


@settings(max_examples=100)
@given(valid_type=st.sampled_from(VALID_TYPES))
def test_valid_resource_types_are_accepted(valid_type: str):
    """Property: Every valid type value is accepted by the validator."""
    payload = _make_valid_payload(valid_type)
    result = CreateResourceRequest.model_validate(payload)
    assert result.type == valid_type


@settings(max_examples=100)
@given(random_string=st.text())
def test_invalid_resource_types_are_rejected(random_string: str):
    """Property: Any string that is NOT one of the 5 allowed values is rejected."""
    assume(random_string not in VALID_TYPES)

    payload = {
        "id": "test-resource",
        "name": "Test Resource",
        "type": random_string,
        "resourceId": "i-0abcdef1234567890",
    }
    with pytest.raises(ValidationError) as exc_info:
        CreateResourceRequest.model_validate(payload)

    # Verify the error is about the type field
    errors = exc_info.value.errors()
    type_errors = [e for e in errors if "type" in e.get("loc", ())]
    assert len(type_errors) > 0, f"Expected validation error on 'type' field for value: {random_string!r}"
