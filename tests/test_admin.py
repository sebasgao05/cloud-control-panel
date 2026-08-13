"""Tests for backend/admin.py - Admin CRUD handlers."""

import json

import bcrypt as _bcrypt
from conftest import (
    TEST_ADMIN_KEY,
    TEST_ADMIN_KEY_ID,
    TEST_API_KEY,
    TEST_KEY_ID,
    TEST_SUPERADMIN_KEY,
    TEST_SUPERADMIN_KEY_ID,
)


class TestHandleCreateAccount:
    """Test handle_create_account."""

    def test_create_account_success(self, seeded_table, reset_utils_table):
        from admin import handle_create_account

        body = {"id": "new-acc", "name": "New Account", "region": "us-east-1"}
        resp = handle_create_account(body)
        assert resp["statusCode"] == 200
        body_data = json.loads(resp["body"])
        assert body_data["id"] == "new-acc"

    def test_create_account_invalid_id(self, seeded_table, reset_utils_table):
        from admin import handle_create_account

        body = {"id": "", "name": "Bad"}
        resp = handle_create_account(body)
        assert resp["statusCode"] == 400

    def test_create_account_missing_name(self, seeded_table, reset_utils_table):
        from admin import handle_create_account

        body = {"id": "valid-id"}
        resp = handle_create_account(body)
        assert resp["statusCode"] == 400


class TestHandleDeleteAccount:
    """Test handle_delete_account."""

    def test_delete_account(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_delete_account

        resp = handle_delete_account("test-account")
        assert resp["statusCode"] == 200
        # Verify account is gone
        item = utils.db_get("CONFIG", "ACCOUNT#test-account")
        assert item is None


class TestHandleCreateInstance:
    """Test handle_create_instance."""

    def test_create_instance_success(self, seeded_table, reset_utils_table):
        from admin import handle_create_instance

        body = {"id": "new-inst", "name": "New Instance", "instanceId": "i-0abcdef123456789a"}
        resp = handle_create_instance("test-account", body)
        assert resp["statusCode"] == 200
        body_data = json.loads(resp["body"])
        assert body_data["id"] == "new-inst"

    def test_create_instance_invalid_instance_id(self, seeded_table, reset_utils_table):
        from admin import handle_create_instance

        body = {"id": "new-inst", "name": "New", "instanceId": "invalid"}
        resp = handle_create_instance("test-account", body)
        assert resp["statusCode"] == 400


class TestHandleDeleteInstance:
    """Test handle_delete_instance."""

    def test_delete_instance(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_delete_instance

        resp = handle_delete_instance("test-account", "inst-1")
        assert resp["statusCode"] == 200
        item = utils.db_get("ACCOUNT#test-account", "INSTANCE#inst-1")
        assert item is None


class TestHandleCreateGroup:
    """Test handle_create_group."""

    def test_create_group_success(self, seeded_table, reset_utils_table):
        from admin import handle_create_group

        body = {"id": "new-grp", "name": "New Group"}
        resp = handle_create_group("test-account", body)
        assert resp["statusCode"] == 200
        body_data = json.loads(resp["body"])
        assert body_data["id"] == "new-grp"

    def test_create_group_invalid_color(self, seeded_table, reset_utils_table):
        from admin import handle_create_group

        body = {"id": "grp2", "name": "Group 2", "color": "not-a-color"}
        resp = handle_create_group("test-account", body)
        assert resp["statusCode"] == 400


class TestHandleDeleteGroup:
    """Test handle_delete_group."""

    def test_delete_group(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_delete_group

        resp = handle_delete_group("test-account", "grp-1")
        assert resp["statusCode"] == 200
        item = utils.db_get("ACCOUNT#test-account", "GROUP#grp-1")
        assert item is None


class TestHandleListKeys:
    """Test handle_list_keys."""

    def test_list_keys_returns_metadata(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_list_keys

        config = utils.load_config_from_db()
        resp = handle_list_keys(config)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        keys = body["keys"]
        assert len(keys) >= 1

    def test_list_keys_never_exposes_hash(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_list_keys

        config = utils.load_config_from_db()
        resp = handle_list_keys(config)
        body = json.loads(resp["body"])
        for key in body["keys"]:
            assert "hash" not in key
            assert "key_preview" in key
            # key_preview is first 8 chars + "..."
            assert key["key_preview"].endswith("...")


class TestHandleCreateKey:
    """Test handle_create_key."""

    def test_create_key_returns_plaintext(self, seeded_table, reset_utils_table):
        from admin import handle_create_key

        body = {"name": "New Key", "role": "operator", "accounts": []}
        resp = handle_create_key(body)
        assert resp["statusCode"] == 200
        body_data = json.loads(resp["body"])
        assert "key" in body_data
        assert "key_id" in body_data
        # Key should be a UUID4 format
        assert len(body_data["key"]) == 36

    def test_create_key_stores_bcrypt_hash(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_create_key

        body = {"name": "Hash Test Key", "role": "operator", "accounts": []}
        resp = handle_create_key(body)
        body_data = json.loads(resp["body"])
        key_id = body_data["key_id"]
        plaintext = body_data["key"]

        # Verify hash is stored in DB
        item = utils.db_get("CONFIG", f"APIKEY#{key_id}")
        assert item is not None
        stored_hash = item["data"]["hash"]
        assert _bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("utf-8"))


class TestHandleCreateKeyValidated:
    """Test handle_create_key_validated with role checks."""

    def test_admin_can_create_operator(self, seeded_table, reset_utils_table):
        from admin import handle_create_key_validated

        body = {"name": "Op Key", "role": "operator", "accounts": []}
        user_info = {"role": "admin"}
        resp = handle_create_key_validated(body, user_info)
        assert resp["statusCode"] == 200

    def test_admin_cannot_create_admin(self, seeded_table, reset_utils_table):
        from admin import handle_create_key_validated

        body = {"name": "Admin Key", "role": "admin", "accounts": []}
        user_info = {"role": "admin"}
        resp = handle_create_key_validated(body, user_info)
        assert resp["statusCode"] == 403

    def test_superadmin_cannot_create_superadmin(self, seeded_table, reset_utils_table):
        from admin import handle_create_key_validated

        body = {"name": "SA Key", "role": "superadmin", "accounts": []}
        user_info = {"role": "superadmin"}
        # Note: CreateKeyRequest only allows "operator" or "admin" for role,
        # so "superadmin" should fail validation
        resp = handle_create_key_validated(body, user_info)
        assert resp["statusCode"] == 400


class TestHandleDeleteKey:
    """Test handle_delete_key with role-based restrictions."""

    def test_self_deletion_prevented(self, seeded_table, reset_utils_table):
        from admin import handle_delete_key

        event = {"headers": {"x-api-key": TEST_SUPERADMIN_KEY}}
        resp = handle_delete_key(TEST_SUPERADMIN_KEY_ID, event)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "propia" in body["error"].lower() or "propia" in body["error"]

    def test_operator_cannot_delete(self, seeded_table, reset_utils_table):
        from admin import handle_delete_key

        event = {"headers": {"x-api-key": TEST_API_KEY}}
        resp = handle_delete_key(TEST_ADMIN_KEY_ID, event)
        assert resp["statusCode"] == 403

    def test_admin_can_delete_operator(self, seeded_table, reset_utils_table):
        from admin import handle_delete_key

        event = {"headers": {"x-api-key": TEST_ADMIN_KEY}}
        resp = handle_delete_key(TEST_KEY_ID, event)
        assert resp["statusCode"] == 200

    def test_admin_cannot_delete_admin(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_delete_key

        # Create another admin key to try to delete
        other_admin_id = "other-admin-id"
        other_hash = _bcrypt.hashpw(b"other-admin-key", _bcrypt.gensalt()).decode("utf-8")
        utils.db_put({
            "PK": "CONFIG",
            "SK": f"APIKEY#{other_admin_id}",
            "data": {"hash": other_hash, "name": "Other Admin", "role": "admin", "accounts": ["*"]},
        })

        event = {"headers": {"x-api-key": TEST_ADMIN_KEY}}
        resp = handle_delete_key(other_admin_id, event)
        assert resp["statusCode"] == 403

    def test_superadmin_cannot_delete_superadmin(self, seeded_table, reset_utils_table):
        import utils
        from admin import handle_delete_key

        other_sa_id = "other-superadmin-id"
        other_hash = _bcrypt.hashpw(b"other-sa-key", _bcrypt.gensalt()).decode("utf-8")
        utils.db_put({
            "PK": "CONFIG",
            "SK": f"APIKEY#{other_sa_id}",
            "data": {"hash": other_hash, "name": "Other SA", "role": "superadmin", "accounts": ["*"]},
        })

        event = {"headers": {"x-api-key": TEST_SUPERADMIN_KEY}}
        resp = handle_delete_key(other_sa_id, event)
        assert resp["statusCode"] == 403

    def test_delete_nonexistent_key(self, seeded_table, reset_utils_table):
        from admin import handle_delete_key

        event = {"headers": {"x-api-key": TEST_SUPERADMIN_KEY}}
        resp = handle_delete_key("nonexistent-key-id", event)
        assert resp["statusCode"] == 404


class TestHandleUpdateKeyAccounts:
    """Test handle_update_key_accounts."""

    def test_update_accounts(self, seeded_table, reset_utils_table):
        from admin import handle_update_key_accounts

        body = {"accounts": ["acc-1", "acc-2"]}
        resp = handle_update_key_accounts(TEST_KEY_ID, body)
        assert resp["statusCode"] == 200
        body_data = json.loads(resp["body"])
        assert body_data["accounts"] == ["acc-1", "acc-2"]

    def test_update_nonexistent_key(self, seeded_table, reset_utils_table):
        from admin import handle_update_key_accounts

        body = {"accounts": ["acc-1"]}
        resp = handle_update_key_accounts("nonexistent", body)
        assert resp["statusCode"] == 404

    def test_update_invalid_accounts(self, seeded_table, reset_utils_table):
        from admin import handle_update_key_accounts

        body = {"accounts": ["valid", "inv@lid!"]}
        resp = handle_update_key_accounts(TEST_KEY_ID, body)
        assert resp["statusCode"] == 400
