# Feature: multi-service-dashboard-iac, Property 13: Uptime state transitions follow activity log entries
"""
Property-based tests for uptime state transitions.

**Validates: Requirements 9.1, 9.5, 9.6**

Property 13: For any sequence of activity log entries containing "start" and "stop"
actions for a resource, the uptime timeline SHALL show "running" for all hours after
a "start" entry (until a "stop" entry), "stopped" for all hours after a "stop" entry
(until a "start" entry), and "unknown" for hours with no preceding activity data.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# Strategy: generate a list of (offset_hours, action) pairs representing activity events
# offset_hours is the number of hours before "now" when the event occurs
# We use integers for offset to align cleanly with hourly intervals
activity_events_strategy = st.lists(
    st.tuples(
        st.integers(min_value=1, max_value=166),  # offset hours within 7-day range (168 hours)
        st.sampled_from(["start", "stop"]),
    ),
    min_size=1,
    max_size=20,
)


def _build_dynamo_items(events, account_id, resource_id, now):
    """Convert (offset_hours, action) pairs into DynamoDB-formatted activity items."""
    items = []
    for offset_hours, action in events:
        # Place event at the middle of the hour (30 min mark) to clearly fall within an interval
        event_time = now - timedelta(hours=offset_hours) + timedelta(minutes=30)
        timestamp_str = event_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        items.append({
            "PK": f"ACTIVITY#{account_id}",
            "SK": timestamp_str,
            "data": {
                "action": action,
                "user": "test-user",
                "resourceIds": [resource_id],
                "timestamp": timestamp_str,
            },
        })
    # Sort by SK (timestamp) to simulate DynamoDB sort order
    items.sort(key=lambda x: x["SK"])
    return items


def _compute_expected_states(events, days, now):
    """Compute expected state for each hourly interval given a sequence of events.

    Returns a list of expected states for each of the days*24 intervals.
    Events are (offset_hours, action) tuples where offset_hours is hours before now.
    """
    total_intervals = days * 24
    start_hour = (now - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)

    # Convert events to (datetime, action) sorted by time
    timed_events = []
    for offset_hours, action in events:
        event_time = now - timedelta(hours=offset_hours) + timedelta(minutes=30)
        timed_events.append((event_time, action))
    timed_events.sort(key=lambda x: x[0])

    # Walk through intervals and determine expected state
    expected_states = []
    current_state = "unknown"  # No preceding activity data means unknown

    event_idx = 0
    for i in range(total_intervals):
        interval_start = start_hour + timedelta(hours=i)
        interval_end = interval_start + timedelta(hours=1)

        # Apply all events that fall within this interval
        while event_idx < len(timed_events):
            event_time, action = timed_events[event_idx]
            if event_time < interval_end:
                if action == "start":
                    current_state = "running"
                elif action == "stop":
                    current_state = "stopped"
                event_idx += 1
            else:
                break

        expected_states.append(current_state)

    return expected_states


@settings(max_examples=100)
@given(events=activity_events_strategy)
def test_start_entries_produce_running_intervals(events):
    """Property: After a 'start' event, intervals are 'running' until a 'stop' event."""
    # Use a fixed "now" to make the test deterministic
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    days = 7
    account_id = "test-account"
    resource_id = "res-1"

    # Build mock DynamoDB items
    dynamo_items = _build_dynamo_items(events, account_id, resource_id, now)

    # Mock db_query_between to return our generated items (filtered by range)
    def mock_db_query_between(pk, sk_start, sk_end):
        return [
            item for item in dynamo_items
            if item["PK"] == pk and sk_start <= item["SK"] <= sk_end
        ]

    # Mock datetime.now to return our fixed time
    with patch("uptime.db_query_between", side_effect=mock_db_query_between):
        with patch("uptime.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat
            mock_datetime.strptime = datetime.strptime
            # Preserve timedelta and timezone access
            from uptime import get_uptime_data
            result = get_uptime_data(account_id, resource_id, days)

    # Compute expected states
    expected_states = _compute_expected_states(events, days, now)

    # Verify the intervals match expected state transitions
    intervals = result["intervals"]
    assert len(intervals) == days * 24

    for i, interval in enumerate(intervals):
        assert interval["state"] == expected_states[i], (
            f"Interval {i} (hour={interval['hour']}): "
            f"expected '{expected_states[i]}', got '{interval['state']}'. "
            f"Events: {sorted(events, key=lambda e: e[0], reverse=True)}"
        )


@settings(max_examples=100)
@given(events=activity_events_strategy)
def test_stop_entries_produce_stopped_intervals(events):
    """Property: After a 'stop' event with no subsequent 'start', intervals are 'stopped'."""
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    days = 7
    account_id = "test-account"
    resource_id = "res-1"

    dynamo_items = _build_dynamo_items(events, account_id, resource_id, now)

    def mock_db_query_between(pk, sk_start, sk_end):
        return [
            item for item in dynamo_items
            if item["PK"] == pk and sk_start <= item["SK"] <= sk_end
        ]

    with patch("uptime.db_query_between", side_effect=mock_db_query_between):
        with patch("uptime.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat
            mock_datetime.strptime = datetime.strptime
            from uptime import get_uptime_data
            result = get_uptime_data(account_id, resource_id, days)

    intervals = result["intervals"]

    # Use the same expected state computation as the main property test
    # to verify "stopped" states appear where expected
    expected_states = _compute_expected_states(events, days, now)

    # If the expected computation says there should be "stopped" intervals,
    # verify the actual result also has them
    if "stopped" in expected_states:
        actual_states = [interval["state"] for interval in intervals]
        assert "stopped" in actual_states, (
            f"Expected 'stopped' intervals but found none. Events: {events}"
        )

    # Verify that every interval marked "stopped" in expected is also "stopped" in actual
    for i, interval in enumerate(intervals):
        if expected_states[i] == "stopped":
            assert interval["state"] == "stopped", (
                f"Interval {i} (hour={interval['hour']}): "
                f"expected 'stopped', got '{interval['state']}'. Events: {events}"
            )


@settings(max_examples=100)
@given(events=activity_events_strategy)
def test_intervals_before_first_event_are_unknown(events):
    """Property: Intervals before any activity event should be 'unknown'."""
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    days = 7
    account_id = "test-account"
    resource_id = "res-1"

    dynamo_items = _build_dynamo_items(events, account_id, resource_id, now)

    def mock_db_query_between(pk, sk_start, sk_end):
        return [
            item for item in dynamo_items
            if item["PK"] == pk and sk_start <= item["SK"] <= sk_end
        ]

    with patch("uptime.db_query_between", side_effect=mock_db_query_between):
        with patch("uptime.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat
            mock_datetime.strptime = datetime.strptime
            from uptime import get_uptime_data
            result = get_uptime_data(account_id, resource_id, days)

    intervals = result["intervals"]
    start_hour = (now - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)

    # Find the earliest event time
    earliest_offset = max(e[0] for e in events)  # largest offset = earliest in time
    earliest_event_time = now - timedelta(hours=earliest_offset) + timedelta(minutes=30)

    # All intervals whose end time is before or at the earliest event should be "unknown"
    for i, interval in enumerate(intervals):
        interval_end = start_hour + timedelta(hours=i + 1)
        if interval_end <= earliest_event_time:
            assert interval["state"] == "unknown", (
                f"Interval {i} (ending {interval_end}) should be 'unknown' "
                f"because earliest event is at {earliest_event_time}. "
                f"Got '{interval['state']}' instead."
            )


@settings(max_examples=100)
@given(events=activity_events_strategy)
def test_all_interval_states_are_valid(events):
    """Property: Every interval state must be one of 'running', 'stopped', or 'unknown'."""
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    days = 7
    account_id = "test-account"
    resource_id = "res-1"

    dynamo_items = _build_dynamo_items(events, account_id, resource_id, now)

    def mock_db_query_between(pk, sk_start, sk_end):
        return [
            item for item in dynamo_items
            if item["PK"] == pk and sk_start <= item["SK"] <= sk_end
        ]

    with patch("uptime.db_query_between", side_effect=mock_db_query_between):
        with patch("uptime.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat
            mock_datetime.strptime = datetime.strptime
            from uptime import get_uptime_data
            result = get_uptime_data(account_id, resource_id, days)

    valid_states = {"running", "stopped", "unknown"}
    for interval in result["intervals"]:
        assert interval["state"] in valid_states, (
            f"Invalid state '{interval['state']}' found in interval {interval['hour']}"
        )
