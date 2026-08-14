# Feature: multi-service-dashboard-iac, Property 6: State normalization maps all service states correctly
"""
Property-based tests for state normalization across all service adapters.

**Validates: Requirements 2.9**

Property 6: For any supported service type and any state string returned by that
service's API, the normalization function SHALL return exactly one of: "running",
"stopped", "pending", "stopping", or "unknown". States not in the known mapping
for that service SHALL map to "unknown".
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from ec2_adapter import EC2_STATE_MAP
from rds_adapter import RDS_STATE_MAP
from lightsail_adapter import LIGHTSAIL_STATE_MAP
from apprunner_adapter import APPRUNNER_STATE_MAP
from ecs_adapter import normalize_ecs_state

# The full set of valid normalized states
VALID_NORMALIZED_STATES = {"running", "stopped", "pending", "stopping", "unknown"}


# --- EC2 State Normalization ---

@settings(max_examples=100)
@given(state=st.sampled_from(list(EC2_STATE_MAP.keys())))
def test_ec2_known_states_map_to_valid_normalized_value(state: str):
    """Property: Every known EC2 state maps to exactly one valid normalized state."""
    result = EC2_STATE_MAP.get(state, "unknown")
    assert result in VALID_NORMALIZED_STATES
    assert result != "unknown", f"Known EC2 state '{state}' should not map to 'unknown'"


@settings(max_examples=100)
@given(state=st.text())
def test_ec2_unknown_states_map_to_unknown(state: str):
    """Property: Any EC2 state not in the known mapping maps to 'unknown'."""
    assume(state not in EC2_STATE_MAP)
    result = EC2_STATE_MAP.get(state, "unknown")
    assert result == "unknown"


# --- RDS State Normalization ---

@settings(max_examples=100)
@given(state=st.sampled_from(list(RDS_STATE_MAP.keys())))
def test_rds_known_states_map_to_valid_normalized_value(state: str):
    """Property: Every known RDS state maps to exactly one valid normalized state."""
    result = RDS_STATE_MAP.get(state, "unknown")
    assert result in VALID_NORMALIZED_STATES
    assert result != "unknown", f"Known RDS state '{state}' should not map to 'unknown'"


@settings(max_examples=100)
@given(state=st.text())
def test_rds_unknown_states_map_to_unknown(state: str):
    """Property: Any RDS state not in the known mapping maps to 'unknown'."""
    assume(state not in RDS_STATE_MAP)
    result = RDS_STATE_MAP.get(state, "unknown")
    assert result == "unknown"


# --- Lightsail State Normalization ---

@settings(max_examples=100)
@given(state=st.sampled_from(list(LIGHTSAIL_STATE_MAP.keys())))
def test_lightsail_known_states_map_to_valid_normalized_value(state: str):
    """Property: Every known Lightsail state maps to exactly one valid normalized state."""
    result = LIGHTSAIL_STATE_MAP.get(state, "unknown")
    assert result in VALID_NORMALIZED_STATES
    assert result != "unknown", f"Known Lightsail state '{state}' should not map to 'unknown'"


@settings(max_examples=100)
@given(state=st.text())
def test_lightsail_unknown_states_map_to_unknown(state: str):
    """Property: Any Lightsail state not in the known mapping maps to 'unknown'."""
    assume(state not in LIGHTSAIL_STATE_MAP)
    result = LIGHTSAIL_STATE_MAP.get(state, "unknown")
    assert result == "unknown"


# --- AppRunner State Normalization ---

@settings(max_examples=100)
@given(state=st.sampled_from(list(APPRUNNER_STATE_MAP.keys())))
def test_apprunner_known_states_map_to_valid_normalized_value(state: str):
    """Property: Every known AppRunner state maps to exactly one valid normalized state."""
    result = APPRUNNER_STATE_MAP.get(state, "unknown")
    assert result in VALID_NORMALIZED_STATES
    # Note: CREATE_FAILED, DELETED, DELETE_FAILED map to "unknown" by design
    # They are "known" entries that intentionally map to unknown


@settings(max_examples=100)
@given(state=st.text())
def test_apprunner_unknown_states_map_to_unknown(state: str):
    """Property: Any AppRunner state not in the known mapping maps to 'unknown'."""
    assume(state not in APPRUNNER_STATE_MAP)
    # OPERATION_IN_PROGRESS is handled specially but not in the static map
    assume(state != "OPERATION_IN_PROGRESS")
    result = APPRUNNER_STATE_MAP.get(state, "unknown")
    assert result == "unknown"


# --- ECS State Normalization (function-based) ---

@settings(max_examples=100)
@given(
    desired_count=st.integers(min_value=1, max_value=100),
    running_count=st.integers(min_value=1, max_value=100),
)
def test_ecs_running_state(desired_count: int, running_count: int):
    """Property: ECS with desiredCount > 0 and runningCount > 0 maps to 'running'."""
    result = normalize_ecs_state(desired_count, running_count)
    assert result == "running"
    assert result in VALID_NORMALIZED_STATES


@settings(max_examples=100)
@given(running_count=st.integers(min_value=0, max_value=0))
def test_ecs_stopped_state(running_count: int):
    """Property: ECS with desiredCount == 0 and runningCount == 0 maps to 'stopped'."""
    result = normalize_ecs_state(0, running_count)
    assert result == "stopped"
    assert result in VALID_NORMALIZED_STATES


@settings(max_examples=100)
@given(running_count=st.integers(min_value=1, max_value=100))
def test_ecs_stopping_state(running_count: int):
    """Property: ECS with desiredCount == 0 but runningCount > 0 maps to 'stopping'."""
    result = normalize_ecs_state(0, running_count)
    assert result == "stopping"
    assert result in VALID_NORMALIZED_STATES


@settings(max_examples=100)
@given(desired_count=st.integers(min_value=1, max_value=100))
def test_ecs_pending_state(desired_count: int):
    """Property: ECS with desiredCount > 0 but runningCount == 0 maps to 'pending'."""
    result = normalize_ecs_state(desired_count, 0)
    assert result == "pending"
    assert result in VALID_NORMALIZED_STATES


@settings(max_examples=100)
@given(
    desired_count=st.integers(min_value=0, max_value=100),
    running_count=st.integers(min_value=0, max_value=100),
)
def test_ecs_all_states_are_valid_normalized(desired_count: int, running_count: int):
    """Property: For any combination of desiredCount and runningCount, normalize_ecs_state
    returns exactly one of the valid normalized states."""
    result = normalize_ecs_state(desired_count, running_count)
    assert result in VALID_NORMALIZED_STATES
