# Feature: multi-service-dashboard-iac, Property 11: Cost calculation produces correct output per resource type
"""
Property-based tests for cost calculation correctness.

**Validates: Requirements 6.1, 6.2, 6.3, 6.5**

Property 11: For any resource of a supported type with a known size designation
in the pricing table, the cost calculation SHALL produce: uptime_hours (non-negative),
hourly_rate (matching the pricing table entry), accumulated_cost (= uptime_hours × hourly_rate),
and monthly_projection. For scale-based services (ECS, AppRunner), uptime_hours SHALL equal
the number of hours with at least one active task/instance. For unknown size designations,
hourly_rate SHALL be $0.00.
"""

import os
import sys
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from cost_estimation import (
    PRICING_TABLES,
    calculate_resource_cost,
    calculate_scale_based_uptime,
    get_hourly_rate,
)

# ─── Strategies ──────────────────────────────────────────────────────────────

resource_types = st.sampled_from(["rds", "ecs", "lightsail", "apprunner"])

# Known size designations per resource type
known_sizes = {
    "rds": list(PRICING_TABLES["rds"].keys()),
    "ecs": list(PRICING_TABLES["ecs"].keys()),
    "lightsail": list(PRICING_TABLES["lightsail"].keys()),
    "apprunner": list(PRICING_TABLES["apprunner"].keys()),
}

# Strategy that generates a (resource_type, size_designation) pair from valid entries
valid_type_and_size = st.one_of(
    *[
        st.tuples(st.just(rt), st.sampled_from(sizes))
        for rt, sizes in known_sizes.items()
    ]
)

uptime_hours_strategy = st.floats(min_value=0, max_value=744, allow_nan=False, allow_infinity=False)

# Strategy for unknown size designations
unknown_sizes = st.text(min_size=1, max_size=30).filter(
    lambda s: all(s not in table for table in PRICING_TABLES.values())
)

# Strategy for day of month (used for now timestamp)
day_of_month = st.integers(min_value=1, max_value=28)


# ─── Tests ───────────────────────────────────────────────────────────────────


@settings(max_examples=100)
@given(type_and_size=valid_type_and_size, uptime=uptime_hours_strategy, day=day_of_month)
def test_cost_calculation_known_size_produces_correct_output(
    type_and_size: tuple, uptime: float, day: int
):
    """Property: For known size designations, cost calculation produces correct fields.

    The output SHALL include: resource_type matching input, uptime_hours (non-negative),
    hourly_rate matching the pricing table entry, accumulated_cost == round(uptime_hours * hourly_rate, 2),
    and monthly_projection (non-negative).
    """
    resource_type, size_designation = type_and_size
    now = datetime(2024, 1, day, 12, 0, 0, tzinfo=timezone.utc)

    result = calculate_resource_cost(resource_type, size_designation, uptime, now)

    # resource_type in output matches input
    assert result["resource_type"] == resource_type

    # uptime_hours is non-negative
    assert result["uptime_hours"] >= 0

    # hourly_rate matches get_hourly_rate from pricing table
    expected_rate = get_hourly_rate(resource_type, size_designation)
    assert result["hourly_rate"] == expected_rate
    assert expected_rate > 0, "Known sizes should have positive hourly rate"

    # accumulated_cost == round(uptime_hours * hourly_rate, 2)
    # Note: the implementation computes cost from the raw uptime_hours,
    # then rounds the output uptime_hours separately for display.
    expected_cost = round(uptime * expected_rate, 2)
    assert result["accumulated_cost"] == expected_cost

    # monthly_projection is non-negative
    assert result["monthly_projection"] >= 0


@settings(max_examples=100)
@given(resource_type=resource_types, unknown_size=unknown_sizes, uptime=uptime_hours_strategy, day=day_of_month)
def test_cost_calculation_unknown_size_returns_zero(
    resource_type: str, unknown_size: str, uptime: float, day: int
):
    """Property: For unknown size designations, hourly_rate SHALL be $0.00 and accumulated_cost $0.00.

    When the size designation is not found in the pricing table, the cost calculation
    returns zero hourly_rate and zero accumulated_cost.
    """
    now = datetime(2024, 1, day, 12, 0, 0, tzinfo=timezone.utc)

    result = calculate_resource_cost(resource_type, unknown_size, uptime, now)

    # resource_type in output matches input
    assert result["resource_type"] == resource_type

    # uptime_hours is non-negative
    assert result["uptime_hours"] >= 0

    # For unknown sizes, hourly_rate == 0.00
    assert result["hourly_rate"] == 0.00

    # accumulated_cost == 0.00
    assert result["accumulated_cost"] == 0.00

    # monthly_projection is non-negative (should be 0.00 as well)
    assert result["monthly_projection"] >= 0


@settings(max_examples=100)
@given(active_hours=st.lists(st.booleans(), min_size=0, max_size=744))
def test_scale_based_uptime_counts_active_hours(active_hours: list):
    """Property: For scale-based services, uptime_hours equals the count of True values.

    For ECS and AppRunner, uptime_hours SHALL equal the number of hours with at
    least one active task/instance. calculate_scale_based_uptime returns a float
    equal to sum(1 for h in active_hours if h).
    """
    result = calculate_scale_based_uptime(active_hours)

    expected = float(sum(1 for h in active_hours if h))
    assert result == expected
    assert result >= 0
    assert result <= len(active_hours)


@settings(max_examples=100)
@given(type_and_size=valid_type_and_size)
def test_get_hourly_rate_matches_pricing_table(type_and_size: tuple):
    """Property: get_hourly_rate returns the exact value from the pricing table.

    For any valid resource_type and known size_designation, the returned rate
    must match the pricing table entry exactly.
    """
    resource_type, size_designation = type_and_size

    rate = get_hourly_rate(resource_type, size_designation)
    expected = PRICING_TABLES[resource_type][size_designation]

    assert rate == expected
    assert rate > 0


@settings(max_examples=100)
@given(resource_type=resource_types, unknown_size=unknown_sizes)
def test_get_hourly_rate_unknown_size_returns_zero(resource_type: str, unknown_size: str):
    """Property: get_hourly_rate returns 0.00 for unknown size designations.

    When the size designation is not in the pricing table for the given type,
    the function SHALL return $0.00.
    """
    rate = get_hourly_rate(resource_type, unknown_size)
    assert rate == 0.00
