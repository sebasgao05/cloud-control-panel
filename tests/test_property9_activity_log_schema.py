# Feature: multi-service-dashboard-iac, Property 9: Activity log entries contain all required fields
"""
Property-based tests for activity log entry schema.

**Validates: Requirements 5.1, 5.3**

Property 9: For any resource action (start or stop) on any supported resource type,
the resulting activity log entry SHALL contain: resource_type (one of the five valid types),
resource_id, resource_name, action, user identifier, and timestamp in valid ISO 8601 UTC format.
"""

import os
import re
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from scheduler import log_activity

# --- Strategies ---

VALID_RESOURCE_TYPES = ["ec2", "rds", "ecs", "lightsail", "apprunner"]
VALID_ACTIONS = ["start", "stop"]

resource_types = st.sampled_from(VALID_RESOURCE_TYPES)
actions = st.sampled_from(VALID_ACTIONS)

# Generate non-empty user names (printable strings)
user_names = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")

# Generate non-empty resource IDs
resource_ids = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")

# Generate non-empty resource names
resource_names = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")

# Generate account IDs
account_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

# ISO 8601 UTC timestamp regex: YYYY-MM-DDTHH:MM:SS.mmmZ
ISO_8601_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@settings(max_examples=100)
@given(
    resource_type=resource_types,
    action=actions,
    user_name=user_names,
    resource_id=resource_ids,
    resource_name=resource_names,
    account_id=account_ids,
)
@patch("scheduler.db_put")
def test_activity_log_entry_contains_all_required_fields(
    mock_db_put: MagicMock,
    resource_type: str,
    action: str,
    user_name: str,
    resource_id: str,
    resource_name: str,
    account_id: str,
):
    """Property: Every activity log entry contains resource_type, resource_id,
    resource_name, action, user, and ISO 8601 UTC timestamp."""
    # Call log_activity
    log_activity(
        account_id,
        action,
        user_name,
        [resource_id],
        resource_type=resource_type,
        resource_name=resource_name,
    )

    # Verify db_put was called
    mock_db_put.assert_called_once()

    # Extract the item written to DynamoDB
    item = mock_db_put.call_args[0][0]
    data = item["data"]

    # Verify "action" field matches input
    assert data["action"] == action, f"Expected action={action}, got {data['action']}"

    # Verify "user" field matches input
    assert data["user"] == user_name, f"Expected user={user_name}, got {data['user']}"

    # Verify "resourceType" field is one of the 5 valid types and matches input
    assert data["resourceType"] in VALID_RESOURCE_TYPES, (
        f"resourceType '{data['resourceType']}' not in valid types"
    )
    assert data["resourceType"] == resource_type

    # Verify "resourceName" field matches input
    assert data["resourceName"] == resource_name, (
        f"Expected resourceName={resource_name}, got {data['resourceName']}"
    )

    # Verify "resourceIds" contains the resource_id
    assert resource_id in data["resourceIds"], (
        f"Expected resource_id '{resource_id}' in resourceIds, got {data['resourceIds']}"
    )

    # Verify "timestamp" matches ISO 8601 UTC format
    assert ISO_8601_UTC_PATTERN.match(data["timestamp"]), (
        f"Timestamp '{data['timestamp']}' does not match ISO 8601 UTC format "
        f"(expected: YYYY-MM-DDTHH:MM:SS.mmmZ)"
    )
