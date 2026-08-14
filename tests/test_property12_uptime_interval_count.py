# Feature: multi-service-dashboard-iac, Property 12: Uptime time range produces correct interval count
"""
Property-based tests for uptime interval count.

**Validates: Requirements 9.2, 9.3**

Property 12: For any current UTC timestamp and a range of N days (7 or 30),
the uptime data function SHALL return exactly N × 24 hourly intervals,
starting from (now - N days) and ending at the current hour.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st


# Strategy: generate UTC datetimes across a wide range
utc_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

# Strategy: the two allowed day ranges
day_ranges = st.sampled_from([7, 30])


@settings(max_examples=100)
@given(now=utc_datetimes, days=day_ranges)
def test_uptime_interval_count_matches_days_times_24(now: datetime, days: int):
    """Property: get_uptime_data returns exactly days * 24 intervals for any timestamp."""
    with patch("uptime.db_query_between", return_value=[]):
        with patch("uptime.datetime") as mock_dt:
            # Mock datetime.now to return the generated timestamp
            mock_dt.now.return_value = now
            # Ensure timedelta and other datetime class methods still work
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            from uptime import get_uptime_data

            result = get_uptime_data("test-account", "resource-1", days)

    expected_count = days * 24
    assert len(result["intervals"]) == expected_count, (
        f"Expected {expected_count} intervals for {days}-day range, got {len(result['intervals'])}"
    )


@settings(max_examples=100)
@given(now=utc_datetimes, days=day_ranges)
def test_7_day_produces_168_and_30_day_produces_720(now: datetime, days: int):
    """Property: 7-day range produces exactly 168 intervals and 30-day range produces exactly 720."""
    with patch("uptime.db_query_between", return_value=[]):
        with patch("uptime.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            from uptime import get_uptime_data

            result = get_uptime_data("test-account", "resource-1", days)

    if days == 7:
        assert len(result["intervals"]) == 168, (
            f"7-day range must produce 168 intervals, got {len(result['intervals'])}"
        )
    elif days == 30:
        assert len(result["intervals"]) == 720, (
            f"30-day range must produce 720 intervals, got {len(result['intervals'])}"
        )


@settings(max_examples=100)
@given(now=utc_datetimes, days=day_ranges)
def test_uptime_intervals_are_hourly_spaced(now: datetime, days: int):
    """Property: All intervals are spaced exactly 1 hour apart."""
    with patch("uptime.db_query_between", return_value=[]):
        with patch("uptime.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            from uptime import get_uptime_data

            result = get_uptime_data("test-account", "resource-1", days)

    intervals = result["intervals"]
    for i in range(1, len(intervals)):
        prev_hour = datetime.strptime(intervals[i - 1]["hour"], "%Y-%m-%dT%H:%M:%SZ")
        curr_hour = datetime.strptime(intervals[i]["hour"], "%Y-%m-%dT%H:%M:%SZ")
        delta_seconds = (curr_hour - prev_hour).total_seconds()
        assert delta_seconds == 3600, (
            f"Intervals at index {i-1} and {i} are not 1 hour apart: "
            f"{intervals[i-1]['hour']} -> {intervals[i]['hour']} (delta={delta_seconds}s)"
        )
