"""Tests for multi-service resource routes in backend/app.py."""

import json
from unittest.mock import MagicMock, patch

from conftest import TEST_API_KEY, TEST_SUPERADMIN_KEY


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


class TestResourceRoutesCRUD:
    """Test resource creation, listing, and deletion routes."""

    def test_list_resources_empty(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        event = make_event(method="GET", path="/api/accounts/test-account/resources", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["resources"] == []

    def test_create_resource_ec2(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "web-server-1",
            "name": "Web Server",
            "type": "ec2",
            "resourceId": "i-0abcdef1234567890",
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["id"] == "web-server-1"
        assert "created" in body["message"]

    def test_create_resource_rds(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "db-cluster-1",
            "name": "Production DB",
            "type": "rds",
            "resourceId": "my-rds-cluster",
            "resourceType": "cluster",
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_create_resource_ecs(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "ecs-service-1",
            "name": "API Service",
            "type": "ecs",
            "resourceId": "prod-cluster/api-service",
            "targetCount": 3,
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_create_resource_invalid_type(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "bad-resource",
            "name": "Bad Resource",
            "type": "invalid",
            "resourceId": "something",
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    def test_create_resource_duplicate_id(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "web-server-1",
            "name": "Web Server",
            "type": "ec2",
            "resourceId": "i-0abcdef1234567890",
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        # Create first
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

        # Try to create duplicate - need to reload config
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "already exists" in body["error"]

    def test_create_resource_operator_forbidden(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        resource_body = {
            "id": "web-server-1",
            "name": "Web Server",
            "type": "ec2",
            "resourceId": "i-0abcdef1234567890",
        }
        event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_API_KEY, body=resource_body,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403

    def test_delete_resource(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        # Create a resource first
        resource_body = {
            "id": "to-delete",
            "name": "Delete Me",
            "type": "lightsail",
            "resourceId": "my-lightsail-instance",
        }
        create_event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        lambda_handler(create_event, None)

        # Delete it
        delete_event = make_event(
            method="DELETE", path="/api/accounts/test-account/resources/to-delete",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(delete_event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "deleted" in body["message"]

    def test_delete_resource_operator_forbidden(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        # Create a resource first
        resource_body = {
            "id": "to-delete",
            "name": "Delete Me",
            "type": "lightsail",
            "resourceId": "my-lightsail-instance",
        }
        create_event = make_event(
            method="POST", path="/api/accounts/test-account/resources",
            api_key=TEST_SUPERADMIN_KEY, body=resource_body,
        )
        lambda_handler(create_event, None)

        # Operator can't delete
        delete_event = make_event(
            method="DELETE", path="/api/accounts/test-account/resources/to-delete",
            api_key=TEST_API_KEY,
        )
        resp = lambda_handler(delete_event, None)
        assert resp["statusCode"] == 403

    def test_delete_resource_not_found(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        event = make_event(
            method="DELETE", path="/api/accounts/test-account/resources/nonexistent",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 404

    def test_resource_invalid_id_format(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        event = make_event(
            method="DELETE", path="/api/accounts/test-account/resources/inv@lid!",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "Invalid resource_id format" in body["error"]


class TestResourceRoutesActions:
    """Test resource action routes (status, start, stop)."""

    def _create_resource(self, seeded_table, resource_id="res-1", resource_type="ec2"):
        """Helper to create a resource in the test table."""
        seeded_table.put_item(
            Item={
                "PK": "ACCOUNT#test-account",
                "SK": f"RESOURCE#{resource_id}",
                "data": {
                    "id": resource_id,
                    "name": "Test Resource",
                    "type": resource_type,
                    "resourceId": "i-0abcdef1234567890",
                },
            }
        )

    @patch("app.get_adapter")
    def test_resource_status(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.status.return_value = {"state": "running", "resourceId": "i-0abcdef1234567890"}
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="GET", path="/api/accounts/test-account/resources/res-1/status",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["state"] == "running"

    @patch("app.get_adapter")
    def test_resource_start(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.start.return_value = {"state": "pending", "message": "Starting resource"}
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="POST", path="/api/accounts/test-account/resources/res-1/start",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["state"] == "pending"

    @patch("app.get_adapter")
    def test_resource_stop(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.stop.return_value = {"state": "stopping", "message": "Stopping resource"}
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="POST", path="/api/accounts/test-account/resources/res-1/stop",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["state"] == "stopping"

    @patch("app.get_adapter")
    def test_resource_action_permission_error(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.start.side_effect = PermissionError("Cross-account access denied for account test-account")
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="POST", path="/api/accounts/test-account/resources/res-1/start",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert "access denied" in body["error"]

    @patch("app.get_adapter")
    def test_resource_action_runtime_error(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.status.side_effect = RuntimeError("Cross-account session expired for account test-account")
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="GET", path="/api/accounts/test-account/resources/res-1/status",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 401
        body = json.loads(resp["body"])
        assert "expired" in body["error"]

    @patch("app.get_adapter")
    def test_resource_action_value_error(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_get_adapter.side_effect = ValueError("Unsupported resource type: unknown")

        event = make_event(
            method="GET", path="/api/accounts/test-account/resources/res-1/status",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "Unsupported" in body["error"]

    @patch("app.get_adapter")
    def test_resource_action_generic_error(self, mock_get_adapter, seeded_table, reset_utils_table):
        from app import lambda_handler

        self._create_resource(seeded_table)

        mock_adapter = MagicMock()
        mock_adapter.stop.side_effect = Exception("Something went wrong")
        mock_get_adapter.return_value = mock_adapter

        event = make_event(
            method="POST", path="/api/accounts/test-account/resources/res-1/stop",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "Resource operation failed" in body["error"]

    def test_resource_action_not_found(self, seeded_table, reset_utils_table):
        from app import lambda_handler

        event = make_event(
            method="GET", path="/api/accounts/test-account/resources/nonexistent/status",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 404


class TestResourceRoutesBackwardCompatibility:
    """Verify existing instance routes still work alongside new resource routes."""

    @patch("ec2_ops.get_ec2_client")
    def test_instances_still_work(self, mock_ec2, seeded_table, reset_utils_table):
        from app import lambda_handler

        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {"Reservations": []}
        mock_ec2.return_value = mock_client

        event = make_event(method="GET", path="/api/accounts/test-account/instances", api_key=TEST_SUPERADMIN_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    @patch("ec2_ops.get_ec2_client")
    def test_instance_status_still_works(self, mock_ec2, seeded_table, reset_utils_table):
        from app import lambda_handler

        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abcdef1234567890", "State": {"Name": "running"}}]}
            ]
        }
        mock_ec2.return_value = mock_client

        event = make_event(
            method="GET", path="/api/accounts/test-account/instances/inst-1/status",
            api_key=TEST_SUPERADMIN_KEY,
        )
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200

    def test_list_resources_operator_can_access(self, seeded_table, reset_utils_table):
        """Operators should be able to list resources for accounts they have access to."""
        from app import lambda_handler

        event = make_event(method="GET", path="/api/accounts/test-account/resources", api_key=TEST_API_KEY)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
