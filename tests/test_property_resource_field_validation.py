# Feature: multi-service-dashboard-iac, Property 2: Resource creation field validation
"""
Property 2: Resource creation field validation

For any resource creation payload, the validator SHALL accept it if and only if:
- `id` is 1-50 alphanumeric characters (plus hyphens/underscores) starting with an alphanumeric character
- `name` is 1-100 characters
- `type` is a valid enum value
- `resourceId` is 1-200 characters
Missing or out-of-bounds fields SHALL be rejected.

**Validates: Requirements 1.2**
"""

import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from validators import CreateResourceRequest


# --- Custom Strategies ---

# Valid characters for id: alphanumeric, hyphens, underscores
ID_CHARS = string.ascii_letters + string.digits + "-_"
ID_START_CHARS = string.ascii_letters + string.digits

# Strategy for a valid id: 1-50 chars, starts with alphanumeric, rest alphanumeric + hyphens/underscores
valid_id_strategy = st.builds(
    lambda start, rest: start + rest,
    start=st.sampled_from(list(ID_START_CHARS)),
    rest=st.text(alphabet=ID_CHARS, min_size=0, max_size=49),
)

# Strategy for a valid name: 1-100 characters (any printable)
valid_name_strategy = st.text(min_size=1, max_size=100).filter(lambda s: s.strip())

# Strategy for valid type
VALID_TYPES = ["ec2", "rds", "ecs", "lightsail", "apprunner"]
valid_type_strategy = st.sampled_from(VALID_TYPES)

# Strategy for valid resourceId based on type
# For generic field-level testing, we use type-appropriate resourceIds
def valid_resource_id_for_type(resource_type: str) -> st.SearchStrategy[str]:
    """Generate valid resourceId values matching the type's format."""
    if resource_type == "ec2":
        # i-[a-f0-9]{8,17}
        return st.builds(
            lambda hex_part: f"i-{hex_part}",
            hex_part=st.text(
                alphabet="0123456789abcdef", min_size=8, max_size=17
            ),
        )
    elif resource_type == "rds":
        # 1-63 alphanumeric + hyphens, starts with alphanumeric
        rds_chars = string.ascii_letters + string.digits + "-"
        return st.builds(
            lambda start, rest: start + rest,
            start=st.sampled_from(list(string.ascii_letters + string.digits)),
            rest=st.text(alphabet=rds_chars, min_size=0, max_size=62),
        ).filter(lambda s: len(s) <= 63)
    elif resource_type == "ecs":
        # 1-200 characters (ARN or cluster/service format)
        return st.text(
            alphabet=string.ascii_letters + string.digits + "/-:_.",
            min_size=1,
            max_size=200,
        )
    elif resource_type == "lightsail":
        # 1-63 chars, alphanumeric, hyphens, and periods, starts with alphanumeric
        ls_chars = string.ascii_letters + string.digits + "-."
        return st.builds(
            lambda start, rest: start + rest,
            start=st.sampled_from(list(string.ascii_letters + string.digits)),
            rest=st.text(alphabet=ls_chars, min_size=0, max_size=62),
        ).filter(lambda s: len(s) <= 63)
    elif resource_type == "apprunner":
        # Starts with "arn:aws:apprunner:", 1-200 chars total
        return st.builds(
            lambda suffix: f"arn:aws:apprunner:{suffix}",
            suffix=st.text(
                alphabet=string.ascii_letters + string.digits + "/-:_",
                min_size=1,
                max_size=182,  # 200 - len("arn:aws:apprunner:")
            ),
        ).filter(lambda s: len(s) <= 200)
    else:
        return st.text(min_size=1, max_size=200)


# Combined strategy for valid payloads
@st.composite
def valid_resource_payload(draw):
    """Generate a complete valid resource creation payload."""
    resource_type = draw(valid_type_strategy)
    resource_id = draw(valid_resource_id_for_type(resource_type))
    return {
        "id": draw(valid_id_strategy),
        "name": draw(valid_name_strategy),
        "type": resource_type,
        "resourceId": resource_id,
    }


# --- Property Tests ---


class TestProperty2ResourceCreationFieldValidation:
    """Property 2: Resource creation field validation.

    For any resource creation payload, the validator SHALL accept it if and only if:
    id is 1-50 alphanumeric characters (plus hyphens/underscores) starting with alphanumeric,
    name is 1-100 characters, type is a valid enum value, and resourceId is 1-200 characters.
    Missing or out-of-bounds fields SHALL be rejected.
    """

    @settings(max_examples=100)
    @given(payload=valid_resource_payload())
    def test_valid_payloads_are_accepted(self, payload):
        """Any payload with valid field constraints SHALL be accepted."""
        # Ensure the id is within bounds after generation
        assume(1 <= len(payload["id"]) <= 50)
        assume(1 <= len(payload["name"]) <= 100)
        assume(1 <= len(payload["resourceId"]) <= 200)

        result = CreateResourceRequest.model_validate(payload)
        assert result.id == payload["id"]
        assert result.name == payload["name"]
        assert result.type == payload["type"]
        assert result.resourceId == payload["resourceId"]

    @settings(max_examples=100)
    @given(
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_empty_id_is_rejected(self, name, resource_type):
        """A payload with an empty id SHALL be rejected."""
        payload = {
            "id": "",
            "name": name,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
        extra_length=st.integers(min_value=51, max_value=100),
    )
    def test_id_too_long_is_rejected(self, name, resource_type, extra_length):
        """A payload with id longer than 50 characters SHALL be rejected."""
        long_id = "a" * extra_length
        payload = {
            "id": long_id,
            "name": name,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        bad_start=st.sampled_from(list("-_!@#$%^&*()+=[]{}|;:',.<>?/ ")),
        rest=st.text(alphabet=ID_CHARS, min_size=0, max_size=48),
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_id_not_starting_with_alphanumeric_is_rejected(
        self, bad_start, rest, name, resource_type
    ):
        """A payload with id not starting with alphanumeric SHALL be rejected."""
        bad_id = bad_start + rest
        assume(1 <= len(bad_id) <= 50)
        payload = {
            "id": bad_id,
            "name": name,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        resource_type=valid_type_strategy,
    )
    def test_empty_name_is_rejected(self, valid_id, resource_type):
        """A payload with an empty name SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "name": "",
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        resource_type=valid_type_strategy,
        extra_length=st.integers(min_value=101, max_value=200),
    )
    def test_name_too_long_is_rejected(self, valid_id, resource_type, extra_length):
        """A payload with name longer than 100 characters SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        long_name = "a" * extra_length
        payload = {
            "id": valid_id,
            "name": long_name,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
        invalid_type=st.text(min_size=1, max_size=50).filter(
            lambda s: s not in ("ec2", "rds", "ecs", "lightsail", "apprunner")
        ),
    )
    def test_invalid_type_is_rejected(self, valid_id, name, invalid_type):
        """A payload with an invalid type value SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "name": name,
            "type": invalid_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_empty_resource_id_is_rejected(self, valid_id, name, resource_type):
        """A payload with an empty resourceId SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "name": name,
            "type": resource_type,
            "resourceId": "",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
        extra_length=st.integers(min_value=201, max_value=300),
    )
    def test_resource_id_too_long_is_rejected(self, valid_id, name, extra_length):
        """A payload with resourceId longer than 200 characters SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        # Use ecs type since it doesn't have additional format constraints beyond length
        long_resource_id = "a" * extra_length
        payload = {
            "id": valid_id,
            "name": name,
            "type": "ecs",
            "resourceId": long_resource_id,
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_missing_id_field_is_rejected(self, name, resource_type):
        """A payload missing the id field SHALL be rejected."""
        payload = {
            "name": name,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        resource_type=valid_type_strategy,
    )
    def test_missing_name_field_is_rejected(self, valid_id, resource_type):
        """A payload missing the name field SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "type": resource_type,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
    )
    def test_missing_type_field_is_rejected(self, valid_id, name):
        """A payload missing the type field SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "name": name,
            "resourceId": "i-0abcdef12345678",
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_missing_resource_id_field_is_rejected(self, valid_id, name, resource_type):
        """A payload missing the resourceId field SHALL be rejected."""
        assume(1 <= len(valid_id) <= 50)
        payload = {
            "id": valid_id,
            "name": name,
            "type": resource_type,
        }
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(
        valid_id=valid_id_strategy,
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_id_boundary_at_exactly_50_chars(self, valid_id, name, resource_type):
        """A payload with id at exactly 50 characters (the max) SHALL be accepted
        if all other constraints are met."""
        # Force id to exactly 50 chars starting with alphanumeric
        exact_id = "a" * 50
        resource_id = "i-0abcdef12345678" if resource_type == "ec2" else "test-resource"
        # For specific types, use appropriate resourceId
        if resource_type == "rds":
            resource_id = "my-rds-instance"
        elif resource_type == "lightsail":
            resource_id = "my-lightsail"
        elif resource_type == "apprunner":
            resource_id = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc"

        payload = {
            "id": exact_id,
            "name": name,
            "type": resource_type,
            "resourceId": resource_id,
        }
        result = CreateResourceRequest.model_validate(payload)
        assert len(result.id) == 50

    @settings(max_examples=100)
    @given(
        name=valid_name_strategy,
        resource_type=valid_type_strategy,
    )
    def test_name_boundary_at_exactly_100_chars(self, name, resource_type):
        """A payload with name at exactly 100 characters (the max) SHALL be accepted."""
        exact_name = "n" * 100
        resource_id = "i-0abcdef12345678" if resource_type == "ec2" else "test-resource"
        if resource_type == "rds":
            resource_id = "my-rds-instance"
        elif resource_type == "lightsail":
            resource_id = "my-lightsail"
        elif resource_type == "apprunner":
            resource_id = "arn:aws:apprunner:us-east-1:123456789012:service/my-svc"

        payload = {
            "id": "valid-id",
            "name": exact_name,
            "type": resource_type,
            "resourceId": resource_id,
        }
        result = CreateResourceRequest.model_validate(payload)
        assert len(result.name) == 100
