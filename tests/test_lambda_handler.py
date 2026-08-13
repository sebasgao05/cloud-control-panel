"""Tests for backend/app.py - Lambda handler routing and integration tests."""

import json
from unittest.mock import MagicMock, patch

from conftest import TEST_ADMIN_KEY, TEST_API_KEY, TEST_SUPERADMIN_KEY


def make_event(method="GET", path="/api/accounts", api_key=None, body=None):
    """Helper to construct a Lambda event."""
    event = {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "headers": {},
    }
    if api_key:
        event["headers"]["x-api-key"] = api_key
    if body is not None:
        event["body"] = json.dumps(body)
    return event


class TestLambdaHandlerRouting:
    """Test lambda_handler routing for various paths."""

    def test_unauthenticated_returns_401(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(path="/api/accounts")
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 401

    def test_invalid_key_returns_401(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(path="/api/accounts", api_key="invalid-key")
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 401

    @patch("ec2_ops.get_ec2_client")
    def test_get_accounts(self, mock_ec2, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/accounts", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "accounts" in body

    def test_unknown_path_returns_404(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/nonexistent", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 404

    def test_get_config_operator_forbidden(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/config", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403

    def test_get_config_superadmin(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/config", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "accounts" in body
        assert "apiKeys" in body

    @patch("ec2_ops.get_ec2_client")
    def test_list_instances(self, mock_ec2, seeded_table, reset_utils_table):
        from app import lambda_handler

        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {"Reservations": []}
        mock_ec2.return_value = mock_client

        event = make_event(method="GET", path="/api/accounts/test-account/instances", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_access_denied_account(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        # Operator only has access to "test-account"
        event = make_event(method="GET", path="/api/accounts/other-account/instances", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403

    def test_scheduler_event_routing(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        with patch("ec2_ops.get_ec2_client") as mock_ec2:
            mock_client = MagicMock()
            mock_ec2.return_value = mock_client
            with patch("scheduler.send_notifications"):
                event = {
                    "source": "scheduler",
                    "action": "start",
                    "accountId": "test-account",
                    "instanceIds": ["i-0abcdef1234567890"],
                    "ruleId": "rule-1",
                }
                result = lambda_handler(event, None)
                assert result["statusCode"] == 200


class TestLambdaHandlerAdmin:
    """Test admin operations via lambda_handler."""

    def test_create_account_non_superadmin_forbidden(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="POST", path="/api/accounts", api_key=TEST_API_KEY, body={"id": "x", "name": "X"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403

    def test_create_account_superadmin(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(
            method="POST", path="/api/accounts", api_key=TEST_SUPERADMIN_KEY,
            body={"id": "new-acc", "name": "New Account", "region": "us-east-1"},
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_delete_account(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="DELETE", path="/api/accounts/test-account", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_list_keys_admin(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/keys/list", api_key=TEST_ADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "keys" in body

    def test_list_keys_operator_forbidden(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="GET", path="/api/keys/list", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403

    def test_create_key_admin(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(
            method="POST", path="/api/keys/create", api_key=TEST_ADMIN_KEY,
            body={"name": "New Key", "role": "operator", "accounts": []},
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "key" in body


class TestLambdaHandlerErrorSanitization:
    """Test that internal errors are sanitized."""

    @patch("app.handle_list_accounts")
    def test_500_error_sanitized(self, mock_handler, seeded_table, reset_utils_table):
        from app import lambda_handler

        mock_handler.side_effect = Exception("Secret internal error message")

        event = make_event(method="GET", path="/api/accounts", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert body["error"] == "Internal server error"
        assert "Secret" not in resp["body"]


class TestLambdaHandlerPathValidation:
    """Test path parameter validation."""

    def test_invalid_account_id_format(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="DELETE", path="/api/accounts/inv@lid!", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    def test_invalid_key_id_format(self, seeded_table, reset_utils_table):
        from app import lambda_handler
        event = make_event(method="DELETE", path="/api/keys/inv@lid!", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
