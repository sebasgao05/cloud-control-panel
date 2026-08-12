"""Tests for backend/auth.py - Authentication, authorization, and permission helpers."""


from conftest import (
    TEST_ADMIN_KEY,
    TEST_ADMIN_KEY_HASH,
    TEST_ADMIN_KEY_ID,
    TEST_API_KEY,
    TEST_API_KEY_HASH,
    TEST_KEY_ID,
)


class TestAuthenticate:
    """Test authenticate() with bcrypt-hashed keys."""

    def test_valid_key_returns_user_info(self):
        from auth import authenticate

        config = {
            "apiKeys": {
                TEST_KEY_ID: {
                    "hash": TEST_API_KEY_HASH,
                    "name": "Test User",
                    "role": "operator",
                    "accounts": ["acc-1"],
                }
            }
        }
        event = {"headers": {"x-api-key": TEST_API_KEY}}
        result = authenticate(event, config)
        assert result is not None
        assert result["name"] == "Test User"
        assert result["role"] == "operator"

    def test_invalid_key_returns_none(self):
        from auth import authenticate

        config = {
            "apiKeys": {
                TEST_KEY_ID: {
                    "hash": TEST_API_KEY_HASH,
                    "name": "Test User",
                    "role": "operator",
                    "accounts": [],
                }
            }
        }
        event = {"headers": {"x-api-key": "wrong-key"}}
        result = authenticate(event, config)
        assert result is None

    def test_missing_header_returns_none(self):
        from auth import authenticate

        config = {"apiKeys": {}}
        event = {"headers": {}}
        result = authenticate(event, config)
        assert result is None

    def test_empty_key_returns_none(self):
        from auth import authenticate

        config = {"apiKeys": {TEST_KEY_ID: {"hash": TEST_API_KEY_HASH, "name": "X", "role": "operator", "accounts": []}}}
        event = {"headers": {"x-api-key": ""}}
        result = authenticate(event, config)
        assert result is None

    def test_legacy_plaintext_key_fallback(self):
        from auth import authenticate

        config = {
            "apiKeys": {
                "legacy-plaintext-key": {
                    "name": "Legacy User",
                    "role": "operator",
                    "accounts": ["*"],
                }
            }
        }
        event = {"headers": {"x-api-key": "legacy-plaintext-key"}}
        result = authenticate(event, config)
        assert result is not None
        assert result["name"] == "Legacy User"

    def test_multiple_keys_finds_correct_one(self):
        from auth import authenticate

        config = {
            "apiKeys": {
                TEST_KEY_ID: {
                    "hash": TEST_API_KEY_HASH,
                    "name": "Operator",
                    "role": "operator",
                    "accounts": ["a"],
                },
                TEST_ADMIN_KEY_ID: {
                    "hash": TEST_ADMIN_KEY_HASH,
                    "name": "Admin",
                    "role": "admin",
                    "accounts": ["*"],
                },
            }
        }
        event = {"headers": {"x-api-key": TEST_ADMIN_KEY}}
        result = authenticate(event, config)
        assert result is not None
        assert result["name"] == "Admin"

    def test_corrupted_hash_skipped(self):
        from auth import authenticate

        config = {
            "apiKeys": {
                "bad-key": {
                    "hash": "not-a-valid-bcrypt-hash",
                    "name": "Bad Key",
                    "role": "operator",
                    "accounts": [],
                },
                TEST_KEY_ID: {
                    "hash": TEST_API_KEY_HASH,
                    "name": "Good Key",
                    "role": "operator",
                    "accounts": [],
                },
            }
        }
        event = {"headers": {"x-api-key": TEST_API_KEY}}
        result = authenticate(event, config)
        assert result is not None
        assert result["name"] == "Good Key"


class TestGetAllowedAccounts:
    """Test get_allowed_accounts with wildcard and specific accounts."""

    def test_wildcard_returns_all(self):
        from auth import get_allowed_accounts

        user_info = {"accounts": ["*"]}
        config = {"accounts": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        result = get_allowed_accounts(user_info, config)
        assert len(result) == 3

    def test_specific_accounts_filtered(self):
        from auth import get_allowed_accounts

        user_info = {"accounts": ["a", "c"]}
        config = {"accounts": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        result = get_allowed_accounts(user_info, config)
        assert len(result) == 2
        assert all(acc["id"] in ("a", "c") for acc in result)

    def test_no_access(self):
        from auth import get_allowed_accounts

        user_info = {"accounts": ["x"]}
        config = {"accounts": [{"id": "a"}, {"id": "b"}]}
        result = get_allowed_accounts(user_info, config)
        assert len(result) == 0


class TestIsAdmin:
    """Test is_admin helper."""

    def test_admin_is_admin(self):
        from auth import is_admin
        assert is_admin({"role": "admin"}) is True

    def test_superadmin_is_admin(self):
        from auth import is_admin
        assert is_admin({"role": "superadmin"}) is True

    def test_operator_is_not_admin(self):
        from auth import is_admin
        assert is_admin({"role": "operator"}) is False

    def test_no_role_is_not_admin(self):
        from auth import is_admin
        assert is_admin({}) is False


class TestIsSuperadmin:
    """Test is_superadmin helper."""

    def test_superadmin_is_superadmin(self):
        from auth import is_superadmin
        assert is_superadmin({"role": "superadmin"}) is True

    def test_admin_is_not_superadmin(self):
        from auth import is_superadmin
        assert is_superadmin({"role": "admin"}) is False

    def test_operator_is_not_superadmin(self):
        from auth import is_superadmin
        assert is_superadmin({"role": "operator"}) is False


class TestFindInstance:
    """Test find_instance helper."""

    def test_found(self):
        from auth import find_instance
        account = {"instances": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        assert find_instance(account, "b") == {"id": "b"}

    def test_not_found(self):
        from auth import find_instance
        account = {"instances": [{"id": "a"}]}
        assert find_instance(account, "z") is None

    def test_empty_instances(self):
        from auth import find_instance
        account = {"instances": []}
        assert find_instance(account, "a") is None


class TestFindGroup:
    """Test find_group helper."""

    def test_found(self):
        from auth import find_group
        account = {"groups": [{"id": "g1"}, {"id": "g2"}]}
        assert find_group(account, "g1") == {"id": "g1"}

    def test_not_found(self):
        from auth import find_group
        account = {"groups": [{"id": "g1"}]}
        assert find_group(account, "z") is None


class TestGetSchedulerPermissions:
    """Test get_scheduler_permissions for different roles."""

    def test_superadmin_full_access(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "superadmin"})
        assert result == {"view": True, "edit": True}

    def test_admin_no_access(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "admin"})
        assert result == {"view": False, "edit": False}

    def test_operator_with_edit(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "operator", "scheduler": {"view": False, "edit": True}})
        assert result == {"view": True, "edit": True}

    def test_operator_view_only(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "operator", "scheduler": {"view": True, "edit": False}})
        assert result == {"view": True, "edit": False}

    def test_operator_no_access(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "operator", "scheduler": {"view": False, "edit": False}})
        assert result == {"view": False, "edit": False}

    def test_operator_no_scheduler_key(self):
        from auth import get_scheduler_permissions
        result = get_scheduler_permissions({"role": "operator"})
        assert result == {"view": False, "edit": False}
