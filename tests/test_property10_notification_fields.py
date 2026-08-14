# Feature: multi-service-dashboard-iac, Property 10: Notifications include resource type and name
"""
Property-based tests for notification message fields.

**Validates: Requirements 5.2**

Property 10: For any notification triggered by a resource action, the notification
message body SHALL contain the resource type and resource name as distinct identifiable
fields that can be programmatically extracted.
"""

import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from notifications import send_notifications

# --- Strategies ---

VALID_RESOURCE_TYPES = ["ec2", "rds", "ecs", "lightsail", "apprunner"]
VALID_EVENTS = ["started", "stopped", "error"]

resource_types = st.sampled_from(VALID_RESOURCE_TYPES)
events = st.sampled_from(VALID_EVENTS)

# Generate non-empty resource names (printable text, no leading/trailing whitespace
# or embedded newlines, since the property focuses on field presence and extractability)
resource_names = (
    st.text(min_size=1, max_size=100)
    .map(lambda s: s.replace("\n", "").replace("\r", "").strip())
    .filter(lambda s: len(s) > 0)
)


@settings(max_examples=100)
@given(
    resource_type=resource_types,
    event=events,
    resource_name=resource_names,
)
@patch("notifications.send_single_notification")
def test_notification_body_contains_resource_type_and_name(
    mock_send: MagicMock,
    resource_type: str,
    event: str,
    resource_name: str,
):
    """Property: Notification message body contains resource_type and resource_name
    as distinct identifiable fields that can be programmatically extracted.

    For any combination of resource type, event, and resource name, the notification
    body SHALL include lines with 'resource_type: {type}' and 'resource_name: {name}'
    as separate, extractable fields.
    """
    mock_send.return_value = True

    # Build an account with notifications enabled and a channel subscribed to all events
    account = {
        "id": "test-account",
        "name": "Test Account",
        "features": {"notifications": True},
        "notifications": {
            "channels": [
                {
                    "id": "ch-1",
                    "name": "Test Channel",
                    "type": "email",
                    "enabled": True,
                    "events": ["started", "stopped", "error"],
                    "config": {"to": "test@example.com"},
                }
            ]
        },
    }

    user_info = {"name": "test-user", "role": "admin"}

    send_notifications(account, event, resource_name, user_info=user_info, resource_type=resource_type)

    # Verify send_single_notification was called
    mock_send.assert_called_once()

    # Extract the message body from the call arguments
    call_args = mock_send.call_args[0]
    # send_single_notification(channel, event, body, subject)
    message_body = call_args[2]

    # Property: resource_type field must be present as a distinct extractable line
    resource_type_lines = [
        line for line in message_body.split("\n")
        if line.startswith("resource_type:")
    ]
    assert len(resource_type_lines) == 1, (
        f"Expected exactly 1 'resource_type:' line, found {len(resource_type_lines)} "
        f"in body:\n{message_body}"
    )

    # Property: resource_name field must be present as a distinct extractable line
    resource_name_lines = [
        line for line in message_body.split("\n")
        if line.startswith("resource_name:")
    ]
    assert len(resource_name_lines) == 1, (
        f"Expected exactly 1 'resource_name:' line, found {len(resource_name_lines)} "
        f"in body:\n{message_body}"
    )

    # Property: the extracted resource_type value matches the input
    extracted_type = resource_type_lines[0].split("resource_type:", 1)[1].strip()
    assert extracted_type == resource_type, (
        f"Expected resource_type='{resource_type}', extracted='{extracted_type}'"
    )

    # Property: the extracted resource_name value matches the input
    extracted_name = resource_name_lines[0].split("resource_name:", 1)[1].strip()
    assert extracted_name == resource_name, (
        f"Expected resource_name='{resource_name}', extracted='{extracted_name}'"
    )
