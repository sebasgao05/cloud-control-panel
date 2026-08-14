"""
Cloud Control Panel - Cost Estimation for Non-EC2 Resources.
Calculates costs for RDS, ECS, Lightsail, and AppRunner resources
using per-type hourly rates based on size designation.
"""

from datetime import datetime, timezone

# ─── Pricing Tables (On-Demand, us-east-1, USD/hour) ─────────────────────

RDS_PRICING = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t3.large": 0.136,
    "db.t3.xlarge": 0.272,
    "db.t3.2xlarge": 0.544,
    "db.r5.large": 0.24,
    "db.r5.xlarge": 0.48,
    "db.r5.2xlarge": 0.96,
    "db.m5.large": 0.171,
    "db.m5.xlarge": 0.342,
    "db.m5.2xlarge": 0.684,
}

ECS_PRICING = {
    "0.25vCPU-0.5GB": 0.01,
    "0.25vCPU-1GB": 0.012,
    "0.25vCPU-2GB": 0.015,
    "0.5vCPU-1GB": 0.025,
    "0.5vCPU-2GB": 0.03,
    "0.5vCPU-4GB": 0.04,
    "1vCPU-2GB": 0.05,
    "1vCPU-4GB": 0.065,
    "1vCPU-8GB": 0.09,
    "2vCPU-4GB": 0.10,
    "2vCPU-8GB": 0.13,
    "2vCPU-16GB": 0.18,
    "4vCPU-8GB": 0.20,
    "4vCPU-16GB": 0.26,
    "4vCPU-30GB": 0.36,
}

LIGHTSAIL_PRICING = {
    "nano": 0.005,
    "micro": 0.01,
    "small": 0.02,
    "medium": 0.04,
    "large": 0.08,
    "xlarge": 0.16,
    "2xlarge": 0.32,
}

APPRUNNER_PRICING = {
    "0.25vCPU-0.5GB": 0.007,
    "0.25vCPU-1GB": 0.01,
    "0.5vCPU-1GB": 0.018,
    "1vCPU-2GB": 0.036,
    "1vCPU-4GB": 0.054,
    "2vCPU-4GB": 0.072,
    "4vCPU-8GB": 0.144,
    "4vCPU-12GB": 0.198,
}

PRICING_TABLES = {
    "rds": RDS_PRICING,
    "ecs": ECS_PRICING,
    "lightsail": LIGHTSAIL_PRICING,
    "apprunner": APPRUNNER_PRICING,
}

# Scale-based services compute cost from hours with >= 1 active task/instance
SCALE_BASED_SERVICES = {"ecs", "apprunner"}


def get_hourly_rate(resource_type: str, size_designation: str) -> float:
    """Get the hourly rate for a resource type and size designation.

    Returns 0.00 if the size designation is not in the pricing table.
    """
    pricing_table = PRICING_TABLES.get(resource_type, {})
    return pricing_table.get(size_designation, 0.00)


def calculate_resource_cost(
    resource_type: str,
    size_designation: str,
    uptime_hours: float,
    now: datetime | None = None,
) -> dict:
    """Calculate cost for a single non-EC2 resource.

    Args:
        resource_type: One of 'rds', 'ecs', 'lightsail', 'apprunner'.
        size_designation: Size identifier (e.g., 'db.t3.medium', '1vCPU-2GB', 'small').
        uptime_hours: Number of hours the resource has been running this month.
            For scale-based services (ECS, AppRunner), this is hours with >= 1 active task/instance.
        now: Current timestamp (defaults to UTC now).

    Returns:
        Dict with: resource_type, uptime_hours, hourly_rate, accumulated_cost, monthly_projection.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    hourly_rate = get_hourly_rate(resource_type, size_designation)
    accumulated_cost = uptime_hours * hourly_rate

    days_elapsed = max(now.day, 1)
    monthly_projection = (accumulated_cost / days_elapsed) * 30 if days_elapsed > 0 else 0

    return {
        "resource_type": resource_type,
        "uptime_hours": round(uptime_hours, 1),
        "hourly_rate": hourly_rate,
        "accumulated_cost": round(accumulated_cost, 2),
        "monthly_projection": round(monthly_projection, 2),
    }


def calculate_scale_based_uptime(active_hours: list[bool]) -> float:
    """Calculate uptime hours for scale-based services (ECS, AppRunner).

    Args:
        active_hours: List of booleans where True means at least one active
            task/instance was running during that hour.

    Returns:
        Number of hours with at least one active task/instance.
    """
    return float(sum(1 for h in active_hours if h))


def is_scale_based(resource_type: str) -> bool:
    """Check if a resource type uses scale-based billing."""
    return resource_type in SCALE_BASED_SERVICES
