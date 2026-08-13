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
