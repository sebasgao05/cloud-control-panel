"""
Unit tests for the uptime chart data endpoint.
Tests the get_uptime_data function and the /uptime route.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def dynamodb_table_with_activity():
    """Create a mocked DynamoDB table with activity log entries."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="test-table",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName="test-table")
        yield table


class TestGetUptimeData:
    """Tests for get_uptime_data function."""

    def test_returns_7_day_intervals_count(self, dynamodb_table_with_activity, reset_utils_table):
        """7-day range should produce exactly 168 intervals."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "web-server-1", 7)
        assert len(result["intervals"]) == 168

    def test_returns_30_day_intervals_count(self, dynamodb_table_with_activity, reset_utils_table):
        """30-day range should produce exactly 720 intervals."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "web-server-1", 30)
        assert len(result["intervals"]) == 720

    def test_no_activity_returns_all_unknown_with_message(self, dynamodb_table_with_activity, reset_utils_table):
        """When no activity data exists, all intervals should be unknown with a message."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "nonexistent-resource", 7)
        assert result["message"] == "No activity data available"
        assert all(i["state"] == "unknown" for i in result["intervals"])

    def test_response_structure(self, dynamodb_table_with_activity, reset_utils_table):
        """Response should contain resourceId, range, and intervals."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "web-server-1", 7)
        assert result["resourceId"] == "web-server-1"
        assert result["range"] == "7d"
        assert "intervals" in result

    def test_30_day_range_label(self, dynamodb_table_with_activity, reset_utils_table):
        """30-day range should have range label '30d'."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "web-server-1", 30)
        assert result["range"] == "30d"

    def test_start_action_transitions_to_running(self, dynamodb_table_with_activity, reset_utils_table):
        """A start action should mark subsequent intervals as 'running'."""
        from uptime import get_uptime_data

        now = datetime.now(timezone.utc)
        # Insert a start event 3 hours ago
        event_time = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": event_time,
                "data": {
                    "action": "start",
                    "user": "admin",
                    "resourceIds": ["web-server-1"],
                    "timestamp": event_time,
                },
            }
        )

        result = get_uptime_data("test-account", "web-server-1", 7)
        # The last few intervals should be "running"
        running_intervals = [i for i in result["intervals"] if i["state"] == "running"]
        assert len(running_intervals) >= 2  # At least 2 hours of running (current + previous)

    def test_stop_action_transitions_to_stopped(self, dynamodb_table_with_activity, reset_utils_table):
        """A stop action should mark subsequent intervals as 'stopped'."""
        from uptime import get_uptime_data

        now = datetime.now(timezone.utc)
        # Insert a stop event 2 hours ago
        event_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": event_time,
                "data": {
                    "action": "stop",
                    "user": "admin",
                    "resourceIds": ["web-server-1"],
                    "timestamp": event_time,
                },
            }
        )

        result = get_uptime_data("test-account", "web-server-1", 7)
        # The last intervals should be "stopped"
        stopped_intervals = [i for i in result["intervals"] if i["state"] == "stopped"]
        assert len(stopped_intervals) >= 1

    def test_start_then_stop_transitions(self, dynamodb_table_with_activity, reset_utils_table):
        """Start followed by stop should show running then stopped intervals."""
        from uptime import get_uptime_data

        now = datetime.now(timezone.utc)
        # Insert start 5 hours ago
        start_time = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": start_time,
                "data": {
                    "action": "start",
                    "user": "admin",
                    "resourceIds": ["web-server-1"],
                    "timestamp": start_time,
                },
            }
        )
        # Insert stop 2 hours ago
        stop_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": stop_time,
                "data": {
                    "action": "stop",
                    "user": "admin",
                    "resourceIds": ["web-server-1"],
                    "timestamp": stop_time,
                },
            }
        )

        result = get_uptime_data("test-account", "web-server-1", 7)
        # Should have both running and stopped intervals
        states = set(i["state"] for i in result["intervals"])
        assert "running" in states
        assert "stopped" in states

    def test_filters_by_resource_id(self, dynamodb_table_with_activity, reset_utils_table):
        """Events for other resources should not affect this resource's timeline."""
        from uptime import get_uptime_data

        now = datetime.now(timezone.utc)
        event_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Insert event for a different resource
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": event_time,
                "data": {
                    "action": "start",
                    "user": "admin",
                    "resourceIds": ["other-resource"],
                    "timestamp": event_time,
                },
            }
        )

        result = get_uptime_data("test-account", "web-server-1", 7)
        # All should be unknown since no events for web-server-1
        assert result.get("message") == "No activity data available"
        assert all(i["state"] == "unknown" for i in result["intervals"])

    def test_intervals_have_valid_hour_format(self, dynamodb_table_with_activity, reset_utils_table):
        """Each interval's hour field should be a valid ISO timestamp."""
        from uptime import get_uptime_data

        result = get_uptime_data("test-account", "web-server-1", 7)
        for interval in result["intervals"]:
            assert "hour" in interval
            # Should parse without error
            dt = datetime.strptime(interval["hour"], "%Y-%m-%dT%H:%M:%SZ")
            assert dt.minute == 0
            assert dt.second == 0

    def test_intervals_only_valid_states(self, dynamodb_table_with_activity, reset_utils_table):
        """All interval states should be one of: running, stopped, unknown."""
        from uptime import get_uptime_data

        now = datetime.now(timezone.utc)
        event_time = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dynamodb_table_with_activity.put_item(
            Item={
                "PK": "ACTIVITY#test-account",
                "SK": event_time,
                "data": {
                    "action": "start",
                    "user": "admin",
                    "resourceIds": ["web-server-1"],
                    "timestamp": event_time,
                },
            }
        )

        result = get_uptime_data("test-account", "web-server-1", 7)
        valid_states = {"running", "stopped", "unknown"}
        for interval in result["intervals"]:
            assert interval["state"] in valid_states


class TestUptimeRoute:
    """Tests for the GET /api/accounts/{id}/resources/{rid}/uptime route."""

    def test_uptime_route_default_7_days(self, seeded_table, reset_utils_table):
        """GET /uptime without range param should default to 7 days."""
        from app import lambda_handler

        # First create a resource
        seeded_table.put_item(
            Item={
                "PK": "ACCOUNT#test-account",
                "SK": "RESOURCE#web-server-1",
                "data": {
                    "id": "web-server-1",
                    "name": "Web Server",
                    "type": "ec2",
                    "resourceId": "i-0abcdef1234567890",
                },
            }
        )

        from conftest import TEST_SUPERADMIN_KEY

        event = {
            "headers": {"x-api-key": TEST_SUPERADMIN_KEY},
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/api/accounts/test-account/resources/web-server-1/uptime",
            "queryStringParameters": None,
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["range"] == "7d"
        assert len(body["intervals"]) == 168

    def test_uptime_route_30_days(self, seeded_table, reset_utils_table):
        """GET /uptime?range=30 should return 30-day data."""
        from app import lambda_handler

        seeded_table.put_item(
            Item={
                "PK": "ACCOUNT#test-account",
                "SK": "RESOURCE#web-server-1",
                "data": {
                    "id": "web-server-1",
                    "name": "Web Server",
                    "type": "ec2",
                    "resourceId": "i-0abcdef1234567890",
                },
            }
        )

        from conftest import TEST_SUPERADMIN_KEY

        event = {
            "headers": {"x-api-key": TEST_SUPERADMIN_KEY},
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/api/accounts/test-account/resources/web-server-1/uptime",
            "queryStringParameters": {"range": "30"},
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["range"] == "30d"
        assert len(body["intervals"]) == 720

    def test_uptime_route_resource_not_found(self, seeded_table, reset_utils_table):
        """GET /uptime for nonexistent resource should return 404."""
        from app import lambda_handler
        from conftest import TEST_SUPERADMIN_KEY

        event = {
            "headers": {"x-api-key": TEST_SUPERADMIN_KEY},
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/api/accounts/test-account/resources/nonexistent/uptime",
            "queryStringParameters": None,
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 404

    def test_uptime_route_invalid_range_defaults_to_7(self, seeded_table, reset_utils_table):
        """GET /uptime?range=invalid should default to 7 days."""
        from app import lambda_handler

        seeded_table.put_item(
            Item={
                "PK": "ACCOUNT#test-account",
                "SK": "RESOURCE#web-server-1",
                "data": {
                    "id": "web-server-1",
                    "name": "Web Server",
                    "type": "ec2",
                    "resourceId": "i-0abcdef1234567890",
                },
            }
        )

        from conftest import TEST_SUPERADMIN_KEY

        event = {
            "headers": {"x-api-key": TEST_SUPERADMIN_KEY},
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/api/accounts/test-account/resources/web-server-1/uptime",
            "queryStringParameters": {"range": "invalid"},
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["range"] == "7d"
        assert len(body["intervals"]) == 168
