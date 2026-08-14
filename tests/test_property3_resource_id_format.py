# Feature: multi-service-dashboard-iac, Property 3: Type-specific resourceId format validation
"""
Property 3: For any resource with a given type, the resourceId validator SHALL accept
the value if and only if it matches the format rules for that type:
  - ec2: matches `i-[a-f0-9]{8,17}`
  - rds: 1-63 alphanumeric characters and hyphens (starts with alphanumeric)
  - ecs: 1-200 characters (ARN or cluster/service format)
  - lightsail: 1-63 characters (alphanumeric, hyphens, periods, starts with alphanumeric)
  - apprunner: 1-200 characters starting with "arn:aws:apprunner:"

**Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.8**
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError


# --- Valid resourceId generators per type ---

def valid_ec2_resource_id():
    """Generate valid EC2 instance IDs: i-[a-f0-9]{8,17}"""
    return st.from_regex(r"i-[a-f0-9]{8,17}", fullmatch=True)


def valid_rds_resource_id():
    """Generate valid RDS identifiers: 1-63 alphanumeric + hyphens, starts with alphanumeric."""
    # First char is alphanumeric, rest can include hyphens
    first_char = st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    rest_chars = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
        min_size=0,
        max_size=62,
    )
    return st.tuples(first_char, rest_chars).map(lambda t: t[0] + t[1])


def valid_ecs_resource_id():
    """Generate valid ECS resource IDs: 1-200 characters (ARN or cluster/service format)."""
    # ECS accepts any string 1-200 chars
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S"),
            blacklist_characters="\x00",
        ),
        min_size=1,
        max_size=200,
    )


def valid_lightsail_resource_id():
    """Generate valid Lightsail instance names: 1-63 chars, alphanumeric + hyphens + periods, starts with alphanumeric."""
    first_char = st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    rest_chars = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.",
        min_size=0,
        max_size=62,
    )
    return st.tuples(first_char, rest_chars).map(lambda t: t[0] + t[1])


def valid_apprunner_resource_id():
    """Generate valid AppRunner service ARNs: starts with 'arn:aws:apprunner:', 1-200 chars total."""
    prefix = "arn:aws:apprunner:"
    # Remaining chars to fill up to max 200
    suffix = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789:/-",
        min_size=1,
        max_size=200 - len(prefix),
    )
    return suffix.map(lambda s: prefix + s)


# --- Invalid resourceId generators per type ---

def invalid_ec2_resource_id():
    """Generate strings that do NOT match the EC2 pattern i-[a-f0-9]{8,17}."""
    return st.one_of(
        # Missing prefix
        st.text(
            alphabet="abcdef0123456789",
            min_size=8,
            max_size=17,
        ),
        # Wrong prefix
        st.text(min_size=1, max_size=30).filter(lambda s: not s.startswith("i-")),
        # Too short hex portion
        st.just("i-").map(lambda p: p + "abc"),
        # Too long hex portion
        st.just("i-").map(lambda p: p + "a" * 18),
        # Contains invalid hex chars
        st.from_regex(r"i-[g-z]{8,17}", fullmatch=True),
    )


def invalid_rds_resource_id():
    """Generate strings that do NOT pass RDS validation."""
    return st.one_of(
        # Too long (>63 chars)
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=64,
            max_size=100,
        ),
        # Starts with hyphen
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=1,
            max_size=62,
        ).map(lambda s: "-" + s),
        # Contains invalid characters (spaces, underscores, special chars)
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_@!",
            min_size=2,
            max_size=63,
        ).filter(lambda s: any(c in s for c in "_@!")),
    )


def invalid_lightsail_resource_id():
    """Generate strings that do NOT pass Lightsail validation."""
    return st.one_of(
        # Too long (>63 chars)
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=64,
            max_size=100,
        ),
        # Starts with hyphen or period
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.",
            min_size=1,
            max_size=62,
        ).map(lambda s: "-" + s),
        # Contains invalid characters
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-._@!#",
            min_size=2,
            max_size=63,
        ).filter(lambda s: any(c in s for c in "_@!#")),
    )


def invalid_apprunner_resource_id():
    """Generate strings that do NOT start with 'arn:aws:apprunner:'."""
    return st.one_of(
        # Random string without the prefix
        st.text(min_size=1, max_size=200).filter(
            lambda s: not s.startswith("arn:aws:apprunner:")
        ),
        # Close but wrong prefix
        st.just("arn:aws:lambda:us-east-1:123456789012:function/test"),
        st.just("arn:azure:apprunner:something"),
    )


# --- Helper to build a valid resource payload ---

def make_resource_payload(resource_type: str, resource_id: str) -> dict:
    """Build a minimal valid resource creation payload."""
    return {
        "id": "test-resource-1",
        "name": "Test Resource",
        "type": resource_type,
        "resourceId": resource_id,
    }


# --- Property tests: Valid resourceIds should be accepted ---

class TestProperty3ValidResourceIds:
    """Test that valid resourceIds for each type are accepted."""

    @settings(max_examples=100)
    @given(resource_id=valid_ec2_resource_id())
    def test_ec2_valid_resource_id_accepted(self, resource_id):
        """EC2 resourceId matching i-[a-f0-9]{8,17} should be accepted."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("ec2", resource_id)
        result = CreateResourceRequest.model_validate(payload)
        assert result.resourceId == resource_id

    @settings(max_examples=100)
    @given(resource_id=valid_rds_resource_id())
    def test_rds_valid_resource_id_accepted(self, resource_id):
        """RDS resourceId with 1-63 alphanumeric+hyphens (starting alphanumeric) should be accepted."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("rds", resource_id)
        result = CreateResourceRequest.model_validate(payload)
        assert result.resourceId == resource_id

    @settings(max_examples=100)
    @given(resource_id=valid_ecs_resource_id())
    def test_ecs_valid_resource_id_accepted(self, resource_id):
        """ECS resourceId of 1-200 characters should be accepted."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("ecs", resource_id)
        result = CreateResourceRequest.model_validate(payload)
        assert result.resourceId == resource_id

    @settings(max_examples=100)
    @given(resource_id=valid_lightsail_resource_id())
    def test_lightsail_valid_resource_id_accepted(self, resource_id):
        """Lightsail resourceId with 1-63 alphanumeric+hyphens+periods (starting alphanumeric) should be accepted."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("lightsail", resource_id)
        result = CreateResourceRequest.model_validate(payload)
        assert result.resourceId == resource_id

    @settings(max_examples=100)
    @given(resource_id=valid_apprunner_resource_id())
    def test_apprunner_valid_resource_id_accepted(self, resource_id):
        """AppRunner resourceId starting with 'arn:aws:apprunner:' (1-200 chars) should be accepted."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("apprunner", resource_id)
        result = CreateResourceRequest.model_validate(payload)
        assert result.resourceId == resource_id


# --- Property tests: Invalid resourceIds should be rejected ---

class TestProperty3InvalidResourceIds:
    """Test that invalid resourceIds for each type are rejected."""

    @settings(max_examples=100)
    @given(resource_id=invalid_ec2_resource_id())
    def test_ec2_invalid_resource_id_rejected(self, resource_id):
        """EC2 resourceId NOT matching i-[a-f0-9]{8,17} should be rejected."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("ec2", resource_id)
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(resource_id=invalid_rds_resource_id())
    def test_rds_invalid_resource_id_rejected(self, resource_id):
        """RDS resourceId violating format rules should be rejected."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("rds", resource_id)
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(resource_id=invalid_lightsail_resource_id())
    def test_lightsail_invalid_resource_id_rejected(self, resource_id):
        """Lightsail resourceId violating format rules should be rejected."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("lightsail", resource_id)
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)

    @settings(max_examples=100)
    @given(resource_id=invalid_apprunner_resource_id())
    def test_apprunner_invalid_resource_id_rejected(self, resource_id):
        """AppRunner resourceId NOT starting with 'arn:aws:apprunner:' should be rejected."""
        from validators import CreateResourceRequest

        payload = make_resource_payload("apprunner", resource_id)
        with pytest.raises(ValidationError):
            CreateResourceRequest.model_validate(payload)
