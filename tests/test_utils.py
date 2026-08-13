"""Tests for backend/utils.py - DynamoDB helpers, response, decimal conversion, migration."""

import json
from decimal import Decimal

from conftest import TEST_KEY_ID


class TestDynamoDBHelpers:
    """Test DynamoDB CRUD operations."""

    def test_db_put_and_get(self, seeded_table, reset_utils_table):
        import utils
        utils.db_put({"PK": "TEST", "SK": "ITEM#1", "data": {"foo": "bar"}})
        item = utils.db_get("TEST", "ITEM#1")
        assert item is not None
        assert item["data"]["foo"] == "bar"

    def test_db_get_nonexistent(self, seeded_table, reset_utils_table):
        import utils
        item = utils.db_get("NONEXISTENT", "NOTHING")
        assert item is None

    def test_db_delete(self, seeded_table, reset_utils_table):
        import utils
        utils.db_put({"PK": "TEST", "SK": "DEL#1", "data": {"x": 1}})
        utils.db_delete("TEST", "DEL#1")
        item = utils.db_get("TEST", "DEL#1")
        assert item is None

    def test_db_query_by_pk(self, seeded_table, reset_utils_table):
        import utils
        utils.db_put({"PK": "QUERY", "SK": "A#1", "data": {"a": 1}})
        utils.db_put({"PK": "QUERY", "SK": "A#2", "data": {"a": 2}})
        utils.db_put({"PK": "QUERY", "SK": "B#1", "data": {"b": 1}})
        items = utils.db_query("QUERY")
        assert len(items) == 3

    def test_db_query_with_sk_prefix(self, seeded_table, reset_utils_table):
        import utils
        utils.db_put({"PK": "QUERY2", "SK": "PREFIX#1", "data": {}})
        utils.db_put({"PK": "QUERY2", "SK": "PREFIX#2", "data": {}})
        utils.db_put({"PK": "QUERY2", "SK": "OTHER#1", "data": {}})
        items = utils.db_query("QUERY2", "PREFIX#")
        assert len(items) == 2


class TestDecimalToNative:
    """Test decimal_to_native conversion."""

    def test_decimal_int(self):
        from utils import decimal_to_native
        assert decimal_to_native(Decimal(42)) == 42
        assert isinstance(decimal_to_native(Decimal(42)), int)

    def test_decimal_float(self):
        from utils import decimal_to_native
        result = decimal_to_native(Decimal("3.14"))
        assert abs(result - 3.14) < 0.001
        assert isinstance(result, float)

    def test_nested_dict(self):
        from utils import decimal_to_native
        data = {"count": Decimal(5), "nested": {"value": Decimal("2.5")}}
        result = decimal_to_native(data)
        assert result == {"count": 5, "nested": {"value": 2.5}}

    def test_list(self):
        from utils import decimal_to_native
        data = [Decimal(1), Decimal(2), Decimal(3)]
        result = decimal_to_native(data)
        assert result == [1, 2, 3]

    def test_passthrough(self):
        from utils import decimal_to_native
        assert decimal_to_native("hello") == "hello"
        assert decimal_to_native(None) is None
        assert decimal_to_native(True) is True


class TestLoadConfigFromDB:
    """Test load_config_from_db reconstructs config correctly."""

    def test_load_config_has_settings(self, seeded_table, reset_utils_table):
        import utils
        config = utils.load_config_from_db()
        assert "settings" in config
        assert config["settings"]["defaultRegion"] == "us-east-1"

    def test_load_config_has_api_keys(self, seeded_table, reset_utils_table):
        import utils
        config = utils.load_config_from_db()
        assert TEST_KEY_ID in config["apiKeys"]
        assert config["apiKeys"][TEST_KEY_ID]["name"] == "Test Operator"

    def test_load_config_has_accounts(self, seeded_table, reset_utils_table):
        import utils
        config = utils.load_config_from_db()
        assert len(config["accounts"]) == 1
        acc = config["accounts"][0]
        assert acc["id"] == "test-account"
        assert len(acc["instances"]) == 2
        assert len(acc["groups"]) == 1

    def test_load_config_has_schedules(self, seeded_table, reset_utils_table):
        import utils
        config = utils.load_config_from_db()
        acc = config["accounts"][0]
        assert len(acc["schedule"]["rules"]) == 1

    def test_load_config_has_channels(self, seeded_table, reset_utils_table):
        import utils
        config = utils.load_config_from_db()
        acc = config["accounts"][0]
        assert len(acc["notifications"]["channels"]) == 2


class TestIsDbInitialized:
    """Test is_db_initialized."""

    def test_initialized_when_settings_exist(self, seeded_table, reset_utils_table):
        import utils
        assert utils.is_db_initialized() is True

    def test_not_initialized_when_empty(self, dynamodb_table, reset_utils_table):
        import utils
        assert utils.is_db_initialized() is False


class TestMigrateJsonToDb:
    """Test migrate_json_to_db."""

    def test_migrate_json_creates_settings(self, dynamodb_table, reset_utils_table):
        import utils
        json_config = {
            "settings": {"defaultRegion": "eu-west-1"},
            "apiKeys": {"key1": {"name": "Key1", "role": "operator", "accounts": []}},
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account 1",
                    "instances": [{"id": "i1", "name": "Inst1"}],
                    "groups": [{"id": "g1", "name": "Grp1"}],
                    "schedule": {"rules": [{"id": "r1", "name": "Rule1"}]},
                    "notifications": {"channels": [{"id": "c1", "name": "Chan1"}]},
                }
            ],
        }
        utils.migrate_json_to_db(json_config)
        assert utils.is_db_initialized() is True
        config = utils.load_config_from_db()
        assert config["settings"]["defaultRegion"] == "eu-west-1"
        assert "key1" in config["apiKeys"]
        assert len(config["accounts"]) == 1
        assert config["accounts"][0]["id"] == "acc1"


class TestMigratePlaintextKeysToBcrypt:
    """Test plaintext key to bcrypt migration."""

    def test_migrate_converts_plaintext_keys(self, dynamodb_table, reset_utils_table):
        import bcrypt as _bcrypt
        import utils

        # Insert a plaintext key (old format)
        dynamodb_table.put_item(Item={
            "PK": "CONFIG",
            "SK": "APIKEY#my-plaintext-key",
            "data": {"name": "Legacy Key", "role": "operator", "accounts": ["*"]},
        })

        utils.migrate_plaintext_keys_to_bcrypt()

        # Old key should be deleted
        old_item = utils.db_get("CONFIG", "APIKEY#my-plaintext-key")
        assert old_item is None

        # New key should exist with a hash
        items = utils.db_query("CONFIG", "APIKEY#")
        assert len(items) >= 1
        # Find the migrated one
        migrated = [i for i in items if i.get("data", {}).get("hash")]
        assert len(migrated) == 1
        stored_hash = migrated[0]["data"]["hash"]
        assert _bcrypt.checkpw(b"my-plaintext-key", stored_hash.encode("utf-8"))

    def test_migrate_skips_already_hashed(self, dynamodb_table, reset_utils_table):
        import utils

        dynamodb_table.put_item(Item={
            "PK": "CONFIG",
            "SK": "APIKEY#some-id",
            "data": {"hash": "already-hashed", "name": "Existing", "role": "admin", "accounts": []},
        })

        utils.migrate_plaintext_keys_to_bcrypt()

        # Should still be there unchanged
        item = utils.db_get("CONFIG", "APIKEY#some-id")
        assert item is not None
        assert item["data"]["hash"] == "already-hashed"

    def test_migrate_sets_flag(self, dynamodb_table, reset_utils_table):
        import utils
        utils.migrate_plaintext_keys_to_bcrypt()
        assert utils.is_keys_migrated() is True

    def test_migrate_idempotent(self, dynamodb_table, reset_utils_table):
        import utils
        dynamodb_table.put_item(Item={
            "PK": "CONFIG",
            "SK": "APIKEY#plaintext1",
            "data": {"name": "Key1", "role": "operator", "accounts": []},
        })
        utils.migrate_plaintext_keys_to_bcrypt()
        # Second call should be a no-op
        utils.migrate_plaintext_keys_to_bcrypt()
        # Only one migrated key + migration flag
        items = utils.db_query("CONFIG", "APIKEY#")
        migrated = [i for i in items if i.get("data", {}).get("name") == "Key1"]
        assert len(migrated) == 1


class TestResponseHelper:
    """Test the response() helper function."""

    def test_response_200(self):
        from utils import response
        resp = response(200, {"message": "ok"})
        assert resp["statusCode"] == 200
        assert resp["headers"]["Content-Type"] == "application/json"
        body = json.loads(resp["body"])
        assert body["message"] == "ok"

    def test_response_error(self):
        from utils import response
        resp = response(404, {"error": "Not found"})
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"] == "Not found"


class TestSanitizeError:
    """Test error sanitization."""

    def test_common_codes(self):
        from utils import sanitize_error
        assert sanitize_error(400) == "Bad request"
        assert sanitize_error(401) == "Unauthorized"
        assert sanitize_error(403) == "Forbidden"
        assert sanitize_error(404) == "Not found"
        assert sanitize_error(500) == "Internal server error"

    def test_unknown_code(self):
        from utils import sanitize_error
        assert sanitize_error(999) == "Internal server error"
