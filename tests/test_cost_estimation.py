"""
Tests for cost estimation of non-EC2 resources (RDS, ECS, Lightsail, AppRunner).
Validates Requirements 6.1, 6.2, 6.3, 6.4, 6.5.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from cost_estimation import (
    APPRUNNER_PRICING,
    ECS_PRICING,
    LIGHTSAIL_PRICING,
    PRICING_TABLES,
    RDS_PRICING,
    SCALE_BASED_SERVICES,
    calculate_resource_cost,
    calculate_scale_based_uptime,
    get_hourly_rate,
    is_scale_based,
)


class TestGetHourlyRate:
    """Test hourly rate lookup for each resource type."""

    def test_rds_known_size(self):
        """Known RDS size returns correct rate."""
        assert get_hourly_rate("rds", "db.t3.medium") == 0.068

    def test_rds_unknown_size_returns_zero(self):
        """Unknown RDS size returns 0.00 (Req 6.3)."""
        assert get_hourly_rate("rds", "db.unknown.size") == 0.00

    def test_ecs_known_size(self):
        """Known ECS size returns correct rate."""
        assert get_hourly_rate("ecs", "1vCPU-2GB") == 0.05

    def test_ecs_unknown_size_returns_zero(self):
        """Unknown ECS size returns 0.00 (Req 6.3)."""
        assert get_hourly_rate("ecs", "unknown-config") == 0.00

    def test_lightsail_known_size(self):
        """Known Lightsail size returns correct rate."""
        assert get_hourly_rate("lightsail", "small") == 0.02

    def test_lightsail_unknown_size_returns_zero(self):
        """Unknown Lightsail size returns 0.00 (Req 6.3)."""
        assert get_hourly_rate("lightsail", "giant") == 0.00

    def test_apprunner_known_size(self):
        """Known AppRunner size returns correct rate."""
        assert get_hourly_rate("apprunner", "1vCPU-2GB") == 0.036

    def test_apprunner_unknown_size_returns_zero(self):
        """Unknown AppRunner size returns 0.00 (Req 6.3)."""
        assert get_hourly_rate("apprunner", "unknown") == 0.00

    def test_unknown_resource_type_returns_zero(self):
        """Unknown resource type returns 0.00."""
        assert get_hourly_rate("unknown_type", "any_size") == 0.00


class TestCalculateResourceCost:
    """Test cost calculation logic for non-EC2 resources (Req 6.1, 6.2, 6.4)."""

    def test_rds_cost_calculation(self):
        """RDS cost is uptime_hours * hourly_rate."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("rds", "db.t3.medium", 100.0, now=now)
        assert result["resource_type"] == "rds"
        assert result["uptime_hours"] == 100.0
        assert result["hourly_rate"] == 0.068
        assert result["accumulated_cost"] == 6.8
        # Projection: (6.8 / 15) * 30 = 13.6
        assert result["monthly_projection"] == 13.6

    def test_ecs_cost_calculation(self):
        """ECS cost uses scale-based uptime hours."""
        now = datetime(2024, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("ecs", "1vCPU-2GB", 50.0, now=now)
        assert result["resource_type"] == "ecs"
        assert result["uptime_hours"] == 50.0
        assert result["hourly_rate"] == 0.05
        assert result["accumulated_cost"] == 2.5
        # Projection: (2.5 / 10) * 30 = 7.5
        assert result["monthly_projection"] == 7.5

    def test_lightsail_cost_calculation(self):
        """Lightsail cost is uptime_hours * hourly_rate."""
        now = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("lightsail", "medium", 200.0, now=now)
        assert result["resource_type"] == "lightsail"
        assert result["uptime_hours"] == 200.0
        assert result["hourly_rate"] == 0.04
        assert result["accumulated_cost"] == 8.0
        # Projection: (8.0 / 20) * 30 = 12.0
        assert result["monthly_projection"] == 12.0

    def test_apprunner_cost_calculation(self):
        """AppRunner cost uses scale-based uptime hours."""
        now = datetime(2024, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("apprunner", "2vCPU-4GB", 30.0, now=now)
        assert result["resource_type"] == "apprunner"
        assert result["uptime_hours"] == 30.0
        assert result["hourly_rate"] == 0.072
        assert result["accumulated_cost"] == 2.16
        # Projection: (2.16 / 5) * 30 = 12.96
        assert result["monthly_projection"] == 12.96

    def test_unknown_size_zero_cost(self):
        """Unknown size produces zero cost but is still included (Req 6.3)."""
        now = datetime(2024, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("rds", "db.unknown", 100.0, now=now)
        assert result["resource_type"] == "rds"
        assert result["hourly_rate"] == 0.00
        assert result["accumulated_cost"] == 0.00
        assert result["monthly_projection"] == 0.00
        # Resource is still included with uptime data
        assert result["uptime_hours"] == 100.0

    def test_zero_uptime_zero_cost(self):
        """Zero uptime hours produces zero cost."""
        now = datetime(2024, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("rds", "db.t3.medium", 0.0, now=now)
        assert result["accumulated_cost"] == 0.00
        assert result["monthly_projection"] == 0.00

    def test_resource_type_in_output(self):
        """Resource type label is included in cost output (Req 6.4)."""
        for resource_type in ["rds", "ecs", "lightsail", "apprunner"]:
            result = calculate_resource_cost(resource_type, "any_size", 10.0)
            assert result["resource_type"] == resource_type

    def test_output_contains_all_required_fields(self):
        """Cost output has: uptime_hours, hourly_rate, accumulated_cost, monthly_projection, resource_type."""
        result = calculate_resource_cost("ecs", "1vCPU-2GB", 24.0)
        required_fields = {"resource_type", "uptime_hours", "hourly_rate", "accumulated_cost", "monthly_projection"}
        assert required_fields.issubset(result.keys())

    def test_first_day_of_month(self):
        """Projection works correctly on day 1."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = calculate_resource_cost("lightsail", "small", 12.0, now=now)
        # days_elapsed = max(1, 1) = 1
        # cost = 12 * 0.02 = 0.24
        # projection = (0.24 / 1) * 30 = 7.2
        assert result["accumulated_cost"] == 0.24
        assert result["monthly_projection"] == 7.2


class TestCalculateScaleBasedUptime:
    """Test scale-based uptime calculation for ECS and AppRunner (Req 6.5)."""

    def test_all_active_hours(self):
        """All hours active returns total hours."""
        active_hours = [True] * 24
        assert calculate_scale_based_uptime(active_hours) == 24.0

    def test_no_active_hours(self):
        """No active hours returns zero."""
        active_hours = [False] * 24
        assert calculate_scale_based_uptime(active_hours) == 0.0

    def test_mixed_active_hours(self):
        """Mixed active/inactive returns count of active hours."""
        active_hours = [True, False, True, True, False, True]
        assert calculate_scale_based_uptime(active_hours) == 4.0

    def test_empty_list(self):
        """Empty list returns zero."""
        assert calculate_scale_based_uptime([]) == 0.0

    def test_single_active_hour(self):
        """Single active hour counts as 1."""
        assert calculate_scale_based_uptime([True]) == 1.0


class TestIsScaleBased:
    """Test scale-based service identification."""

    def test_ecs_is_scale_based(self):
        """ECS is a scale-based service (Req 6.5)."""
        assert is_scale_based("ecs") is True

    def test_apprunner_is_scale_based(self):
        """AppRunner is a scale-based service (Req 6.5)."""
        assert is_scale_based("apprunner") is True

    def test_rds_is_not_scale_based(self):
        """RDS is not scale-based."""
        assert is_scale_based("rds") is False

    def test_lightsail_is_not_scale_based(self):
        """Lightsail is not scale-based."""
        assert is_scale_based("lightsail") is False

    def test_unknown_type_is_not_scale_based(self):
        """Unknown types are not scale-based."""
        assert is_scale_based("unknown") is False


class TestPricingTables:
    """Test that pricing tables exist for all required resource types (Req 6.2)."""

    def test_rds_pricing_table_exists(self):
        assert "rds" in PRICING_TABLES
        assert len(RDS_PRICING) > 0

    def test_ecs_pricing_table_exists(self):
        assert "ecs" in PRICING_TABLES
        assert len(ECS_PRICING) > 0

    def test_lightsail_pricing_table_exists(self):
        assert "lightsail" in PRICING_TABLES
        assert len(LIGHTSAIL_PRICING) > 0

    def test_apprunner_pricing_table_exists(self):
        assert "apprunner" in PRICING_TABLES
        assert len(APPRUNNER_PRICING) > 0

    def test_all_rates_are_positive(self):
        """All pricing table entries are positive numbers."""
        for resource_type, table in PRICING_TABLES.items():
            for size, rate in table.items():
                assert rate > 0, f"{resource_type}/{size} has non-positive rate: {rate}"
