"""Tests for backend/scheduler.py - Scheduler handlers and cron conversion."""

import json
from unittest.mock import MagicMock, patch


class TestCronToEventbridge:
    """Test cron_to_eventbridge conversion."""

    def test_basic_weekday_cron(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("0 7 * * 1-5", "America/Bogota")
        assert result == "cron(0 7 ? * MON-FRI *)"

    def test_single_day(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("30 6 * * 0", "UTC")
        assert result == "cron(30 6 ? * SUN *)"

    def test_multiple_days(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("0 8 * * 1,3,5", "UTC")
        assert result == "cron(0 8 ? * MON,WED,FRI *)"

    def test_invalid_cron_too_few_parts(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("0 7 *", "UTC")
        assert result is None

    def test_empty_cron(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("", "UTC")
        assert result is None

    def test_day_7_maps_to_sun(self):
        from scheduler import cron_to_eventbridge
        result = cron_to_eventbridge("0 9 * * 7", "UTC")
        assert result == "cron(0 9 ? * SUN *)"


class TestHandleGetSchedule:
    """Test handle_get_schedule."""

    def test_schedule_disabled(self):
        from scheduler import handle_get_schedule
        account = {"features": {"scheduler": False}, "schedule": {}, "instances": []}
        user_info = {"role": "superadmin"}
        resp = handle_get_schedule(account, user_info)
        body = json.loads(resp["body"])
        assert body["enabled"] is False

    def test_schedule_enabled_superadmin(self):
        from scheduler import handle_get_schedule
        account = {
            "features": {"scheduler": True},
            "schedule": {"timezone": "UTC", "rules": [{"id": "r1"}]},
            "instances": [{"id": "i1", "name": "Inst1"}],
        }
        user_info = {"role": "superadmin"}
        resp = handle_get_schedule(account, user_info)
        body = json.loads(resp["body"])
        assert body["enabled"] is True
        assert body["permissions"]["view"] is True
        assert body["permissions"]["edit"] is True
        assert body["schedule"]["rules"][0]["id"] == "r1"

    def test_schedule_no_view_permission(self):
        from scheduler import handle_get_schedule
        account = {"features": {"scheduler": True}, "schedule": {}, "instances": []}
        user_info = {"role": "operator", "scheduler": {"view": False, "edit": False}}
        resp = handle_get_schedule(account, user_info)
        body = json.loads(resp["body"])
        assert body["enabled"] is True
        assert body["permissions"]["view"] is False
        assert body["schedule"] is None


class TestHandleUpdateSchedule:
    """Test handle_update_schedule."""

    @patch("scheduler.create_eventbridge_schedule")
    @patch("scheduler.delete_eventbridge_schedule")
    @patch("scheduler.send_notifications")
    def test_update_schedule_success(self, mock_notify, mock_del, mock_create, seeded_table, reset_utils_table):
        from scheduler import handle_update_schedule

        account = {
            "id": "test-account",
            "features": {"scheduler": True},
            "schedule": {"timezone": "America/Bogota", "rules": []},
            "instances": [{"id": "inst-1", "instanceId": "i-001"}],
        }
        user_info = {"role": "superadmin", "name": "Admin"}
        body = {
            "timezone": "America/Bogota",
            "rules": [
                {"id": "rule-new", "startCron": "0 8 * * 1-5", "stopCron": "0 18 * * 1-5", "instances": ["inst-1"], "enabled": True}
            ],
        }

        resp = handle_update_schedule(account, "test-account", user_info, body)
        assert resp["statusCode"] == 200
        mock_create.assert_called()

    @patch("scheduler.send_notifications")
    def test_update_schedule_no_permission(self, mock_notify, seeded_table, reset_utils_table):
        from scheduler import handle_update_schedule

        account = {"id": "test-account", "features": {"scheduler": True}, "schedule": {}, "instances": []}
        user_info = {"role": "operator", "scheduler": {"view": True, "edit": False}}
        body = {"rules": []}

        resp = handle_update_schedule(account, "test-account", user_info, body)
        body_data = json.loads(resp["body"])
        assert body_data.get("denied") is True


class TestHandleSchedulerEvent:
    """Test handle_scheduler_event."""

    @patch("scheduler.send_notifications")
    @patch("ec2_ops.get_ec2_client")
    def test_start_event(self, mock_get_ec2, mock_notify, seeded_table, reset_utils_table):
        from scheduler import handle_scheduler_event

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        event = {
            "action": "start",
            "accountId": "test-account",
            "instanceIds": ["i-0abcdef1234567890"],
            "ruleId": "rule-1",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200
        mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-0abcdef1234567890"])

    @patch("scheduler.send_notifications")
    @patch("ec2_ops.get_ec2_client")
    def test_stop_event(self, mock_get_ec2, mock_notify, seeded_table, reset_utils_table):
        from scheduler import handle_scheduler_event

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        event = {
            "action": "stop",
            "accountId": "test-account",
            "instanceIds": ["i-0abcdef1234567890"],
            "ruleId": "rule-1",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200
        mock_ec2.stop_instances.assert_called_once()

    def test_invalid_event_missing_action(self, seeded_table, reset_utils_table):
        from scheduler import handle_scheduler_event
        event = {"accountId": "test-account", "instanceIds": ["i-001"]}
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 400

    def test_invalid_event_missing_account(self, seeded_table, reset_utils_table):
        from scheduler import handle_scheduler_event
        event = {"action": "start", "instanceIds": ["i-001"]}
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 400

    def test_account_not_found(self, seeded_table, reset_utils_table):
        from scheduler import handle_scheduler_event
        event = {"action": "start", "accountId": "nonexistent", "instanceIds": ["i-001"]}
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 404

    @patch("scheduler.send_notifications")
    @patch("resource_adapter.get_adapter")
    def test_resource_start_dispatches_adapter(self, mock_get_adapter, mock_notify, seeded_table, reset_utils_table):
        """Test that resourceIds trigger the adapter dispatch path."""
        from scheduler import handle_scheduler_event

        # Add a resource to the account in DB
        from utils import db_put
        db_put({
            "PK": "ACCOUNT#test-account",
            "SK": "RESOURCE#rds-db-1",
            "data": {"id": "rds-db-1", "name": "Production DB", "type": "rds", "resourceId": "my-rds-cluster"},
        })

        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        event = {
            "action": "start",
            "accountId": "test-account",
            "resourceIds": ["rds-db-1"],
            "ruleId": "rule-2",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200
        mock_get_adapter.assert_called_once()
        mock_adapter.start.assert_called_once()

    @patch("scheduler.send_notifications")
    @patch("resource_adapter.get_adapter")
    def test_resource_stop_dispatches_adapter(self, mock_get_adapter, mock_notify, seeded_table, reset_utils_table):
        """Test that stop action on resourceIds triggers adapter.stop()."""
        from scheduler import handle_scheduler_event
        from utils import db_put

        db_put({
            "PK": "ACCOUNT#test-account",
            "SK": "RESOURCE#ecs-svc-1",
            "data": {"id": "ecs-svc-1", "name": "ECS Service", "type": "ecs", "resourceId": "cluster/service"},
        })

        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        event = {
            "action": "stop",
            "accountId": "test-account",
            "resourceIds": ["ecs-svc-1"],
            "ruleId": "rule-3",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200
        mock_get_adapter.assert_called_once()
        mock_adapter.stop.assert_called_once()

    @patch("scheduler.send_notifications")
    @patch("resource_adapter.get_adapter")
    def test_resource_event_logs_activity_with_type(self, mock_get_adapter, mock_notify, seeded_table, reset_utils_table):
        """Test that resource events log activity with resource_type field."""
        from scheduler import handle_scheduler_event
        from utils import db_put, db_query

        db_put({
            "PK": "ACCOUNT#test-account",
            "SK": "RESOURCE#ls-inst-1",
            "data": {"id": "ls-inst-1", "name": "Lightsail Web", "type": "lightsail", "resourceId": "my-instance"},
        })

        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        event = {
            "action": "start",
            "accountId": "test-account",
            "resourceIds": ["ls-inst-1"],
            "ruleId": "rule-4",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200

        # Check activity log includes resource_type
        items = db_query("ACTIVITY#test-account")
        assert len(items) == 1
        data = items[0]["data"]
        assert data["resourceType"] == "lightsail"
        assert data["resourceName"] == "Lightsail Web"
        assert data["action"] == "start"

    @patch("scheduler.send_notifications")
    @patch("resource_adapter.get_adapter")
    def test_resource_not_found_returns_error(self, mock_get_adapter, mock_notify, seeded_table, reset_utils_table):
        """Test that a missing resource ID results in an error."""
        from scheduler import handle_scheduler_event

        event = {
            "action": "start",
            "accountId": "test-account",
            "resourceIds": ["nonexistent-resource"],
            "ruleId": "rule-5",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 500
        assert "not found" in result["body"]

    @patch("scheduler.send_notifications")
    @patch("resource_adapter.get_adapter")
    def test_resource_event_unknown_action(self, mock_get_adapter, mock_notify, seeded_table, reset_utils_table):
        """Test that an unknown action with resourceIds returns 400."""
        from scheduler import handle_scheduler_event
        from utils import db_put

        db_put({
            "PK": "ACCOUNT#test-account",
            "SK": "RESOURCE#res-1",
            "data": {"id": "res-1", "name": "Res 1", "type": "ec2", "resourceId": "i-abc123"},
        })

        event = {
            "action": "restart",
            "accountId": "test-account",
            "resourceIds": ["res-1"],
            "ruleId": "rule-6",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 400

    @patch("scheduler.send_notifications")
    @patch("ec2_ops.get_ec2_client")
    def test_legacy_ec2_event_records_resource_type(self, mock_get_ec2, mock_notify, seeded_table, reset_utils_table):
        """Test that legacy EC2 events now record resource_type='ec2' in activity log."""
        from scheduler import handle_scheduler_event
        from utils import db_query

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        event = {
            "action": "start",
            "accountId": "test-account",
            "instanceIds": ["i-0abcdef1234567890"],
            "ruleId": "rule-1",
        }
        result = handle_scheduler_event(event)
        assert result["statusCode"] == 200

        items = db_query("ACTIVITY#test-account")
        assert len(items) == 1
        assert items[0]["data"]["resourceType"] == "ec2"


class TestLogActivity:
    """Test log_activity."""

    def test_log_creates_entry(self, seeded_table, reset_utils_table):
        import utils
        from scheduler import log_activity

        log_activity("test-account", "start", "Admin", ["i-001"], "rule-1")
        items = utils.db_query("ACTIVITY#test-account")
        assert len(items) == 1
        assert items[0]["data"]["action"] == "start"
        assert items[0]["data"]["user"] == "Admin"
        assert items[0]["data"]["resourceIds"] == ["i-001"]
        assert items[0]["data"]["ruleId"] == "rule-1"

    def test_log_includes_resource_type_and_name(self, seeded_table, reset_utils_table):
        import utils
        from scheduler import log_activity

        log_activity(
            "test-account", "stop", "operator@test.com", ["i-0abc123def"],
            resource_type="ec2", resource_name="API Server"
        )
        items = utils.db_query("ACTIVITY#test-account")
        assert len(items) == 1
        data = items[0]["data"]
        assert data["resourceType"] == "ec2"
        assert data["resourceName"] == "API Server"
        assert data["action"] == "stop"
        assert data["user"] == "operator@test.com"
        assert data["resourceIds"] == ["i-0abc123def"]

    def test_log_timestamp_is_iso8601_utc(self, seeded_table, reset_utils_table):
        import re

        import utils
        from scheduler import log_activity

        log_activity("test-account", "start", "Admin", ["i-001"])
        items = utils.db_query("ACTIVITY#test-account")
        ts = items[0]["data"]["timestamp"]
        # ISO 8601 UTC format with milliseconds: YYYY-MM-DDTHH:MM:SS.mmmZ
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)

    def test_log_retry_on_failure(self, seeded_table, reset_utils_table):
        """Test that log_activity retries once on DynamoDB failure and doesn't raise."""
        from unittest.mock import patch

        from scheduler import log_activity

        call_count = {"n": 0}
        original_db_put = None

        def failing_then_success(item):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("DynamoDB write failed")
            # Second call succeeds
            original_db_put(item)

        import utils
        original_db_put = utils.db_put

        with patch("scheduler.db_put", side_effect=failing_then_success):
            # Should not raise
            log_activity("test-account", "start", "Admin", ["i-001"])

        assert call_count["n"] == 2

    def test_log_retry_both_fail_logs_error(self, seeded_table, reset_utils_table):
        """Test that when both attempts fail, error is logged but no exception raised."""
        from unittest.mock import patch

        from scheduler import log_activity

        with patch("scheduler.db_put", side_effect=Exception("DynamoDB unavailable")):
            with patch("scheduler.logger") as mock_logger:
                # Should not raise
                log_activity("test-account", "start", "Admin", ["i-001"])
                mock_logger.warning.assert_called_once()
                mock_logger.error.assert_called_once()

    def test_log_without_resource_type_fields(self, seeded_table, reset_utils_table):
        """Test backward compatibility: resource_type and resource_name default to None when not provided."""
        import utils
        from scheduler import log_activity

        log_activity("test-account", "start", "Admin", ["i-001"])
        items = utils.db_query("ACTIVITY#test-account")
        data = items[0]["data"]
        # Fields are always present in the schema, defaulting to None when not provided
        assert data["resourceType"] is None
        assert data["resourceName"] is None


class TestHandleGetActivity:
    """Test handle_get_activity."""

    def test_get_activity(self, seeded_table, reset_utils_table):
        from scheduler import handle_get_activity, log_activity

        log_activity("test-account", "start", "User", ["i-001"])
        log_activity("test-account", "stop", "User", ["i-001"])

        resp = handle_get_activity("test-account")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["activities"]) == 2
