"""
Cloud Control Panel - Uptime chart data provider.
Builds hourly uptime timelines from Activity_Log entries in DynamoDB.
"""

from datetime import datetime, timedelta, timezone

from utils import db_query_between, decimal_to_native


def get_uptime_data(account_id: str, resource_id: str, days: int) -> dict:
    """Build hourly uptime timeline from Activity_Log entries.

    Queries DynamoDB Activity_Log entries for the given account, filters
    by resource_id, and builds an hourly interval timeline showing
    running/stopped/unknown state for each hour.

    Args:
        account_id: The account identifier.
        resource_id: The resource identifier to filter activity entries.
        days: Number of days to look back (7 or 30).

    Returns:
        Dict with resourceId, range, intervals list, and optional message.
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)

    # Truncate to the start of the hour
    start_hour = start_time.replace(minute=0, second=0, microsecond=0)
    end_hour = now.replace(minute=0, second=0, microsecond=0)

    # Build the list of hourly intervals
    total_intervals = days * 24
    intervals = []
    current = start_hour
    for _ in range(total_intervals):
        intervals.append({"hour": current.strftime("%Y-%m-%dT%H:%M:%SZ"), "state": "unknown"})
        current += timedelta(hours=1)

    # Query activity log entries within the time range
    pk = f"ACTIVITY#{account_id}"
    sk_start = start_hour.strftime("%Y-%m-%dT%H:%M:%SZ")
    sk_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    items = db_query_between(pk, sk_start, sk_end)

    # Filter entries that affect this specific resource
    resource_events = []
    for item in items:
        data = decimal_to_native(item.get("data", {}))
        # Activity log entries store affected resource IDs in different fields
        affected_ids = data.get("resourceIds", []) or data.get("instanceIds", []) or []
        if resource_id in affected_ids:
            timestamp_str = item.get("SK", "") or data.get("timestamp", "")
            action = data.get("action", "")
            if timestamp_str and action in ("start", "stop"):
                resource_events.append({"timestamp": timestamp_str, "action": action})

    # Sort events by timestamp
    resource_events.sort(key=lambda e: e["timestamp"])

    # If no events found, return all-unknown with message
    if not resource_events:
        range_label = f"{days}d"
        return {
            "resourceId": resource_id,
            "range": range_label,
            "intervals": intervals,
            "message": "No activity data available",
        }

    # Build state transitions: walk through intervals and apply events
    # For each interval, determine state based on the most recent event before/during that hour
    current_state = "unknown"

    # Check for events before the start of our range to establish initial state
    # Query a bit before our range to find the last event
    pre_range_start = "0000-00-00T00:00:00Z"
    pre_range_end = sk_start
    pre_items = db_query_between(pk, pre_range_start, pre_range_end)

    # Find the latest event before our range that affects this resource
    for item in reversed(pre_items):
        data = decimal_to_native(item.get("data", {}))
        affected_ids = data.get("resourceIds", []) or data.get("instanceIds", []) or []
        if resource_id in affected_ids:
            action = data.get("action", "")
            if action == "start":
                current_state = "running"
            elif action == "stop":
                current_state = "stopped"
            break

    # Now walk through each interval and apply events that fall within that hour
    event_idx = 0
    for i, interval in enumerate(intervals):
        interval_start = start_hour + timedelta(hours=i)
        interval_end = interval_start + timedelta(hours=1)

        # Apply all events that fall within this hour
        while event_idx < len(resource_events):
            event_ts_str = resource_events[event_idx]["timestamp"]
            try:
                # Handle both formats: with and without fractional seconds
                if "." in event_ts_str:
                    event_ts = datetime.fromisoformat(event_ts_str.replace("Z", "+00:00"))
                else:
                    event_ts = datetime.strptime(event_ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                event_idx += 1
                continue

            if event_ts < interval_end:
                action = resource_events[event_idx]["action"]
                if action == "start":
                    current_state = "running"
                elif action == "stop":
                    current_state = "stopped"
                event_idx += 1
            else:
                break

        # Set the interval state
        interval["state"] = current_state

    range_label = f"{days}d"
    return {
        "resourceId": resource_id,
        "range": range_label,
        "intervals": intervals,
    }
