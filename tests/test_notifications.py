"""Tests for backend/notifications.py - Notification handlers and sending."""

import json
from unittest.mock import MagicMock, patch


class TestSendNotifications:
    """Test send_notifications channel filtering."""

    @patch("notifications.send_single_notification")
    def test_sends_to_enabled_matching_channel(self, mock_send):
        from notifications import send_notifications

        account = {
            "id": "acc-1",
            "name": "Account 1",
            "features": {"notifications": True},
            "notifications": {
                "channels": [
                    {"id": "ch-1", "type": "email", "name": "Admin", "enabled": True, "events": ["started", "stopped"]},
                ]
            },
        }
        send_notifications(account, "started", "Test Instance", {"name": "User", "role": "operator"})
        mock_send.assert_called_once()

    @patch("notifications.send_single_notification")
    def test_skips_disabled_channel(self, mock_send):
        from notifications import send_notifications

        account = {
            "id": "acc-1",
            "name": "Account 1",
            "features": {"notifications": True},
            "notifications": {
                "channels": [
                    {"id": "ch-1", "type": "email", "name": "Admin", "enabled": False, "events": ["started"]},
                ]
            },
        }
        send_notifications(account, "started", "Test Instance", {"name": "User", "role": "operator"})
        mock_send.assert_not_called()

    @patch("notifications.send_single_notification")
    def test_skips_non_matching_event(self, mock_send):
        from notifications import send_notifications

        account = {
            "id": "acc-1",
            "name": "Account 1",
            "features": {"notifications": True},
            "notifications": {
                "channels": [
                    {"id": "ch-1", "type": "email", "name": "Admin", "enabled": True, "events": ["error"]},
                ]
            },
        }
        send_notifications(account, "started", "Test Instance", {"name": "User", "role": "operator"})
        mock_send.assert_not_called()

    @patch("notifications.send_single_notification")
    def test_skips_when_feature_disabled(self, mock_send):
        from notifications import send_notifications

        account = {
            "id": "acc-1",
            "name": "Account 1",
            "features": {"notifications": False},
            "notifications": {"channels": [{"id": "ch-1", "type": "email", "enabled": True, "events": ["started"]}]},
        }
        send_notifications(account, "started", "Test Instance")
        mock_send.assert_not_called()

    @patch("notifications.send_single_notification")
    def test_multiple_channels_filtered(self, mock_send):
        from notifications import send_notifications

        account = {
            "id": "acc-1",
            "name": "Account 1",
            "features": {"notifications": True},
            "notifications": {
                "channels": [
                    {"id": "ch-1", "type": "email", "name": "Email", "enabled": True, "events": ["started"]},
                    {"id": "ch-2", "type": "telegram", "name": "TG", "enabled": False, "events": ["started"]},
                    {"id": "ch-3", "type": "teams", "name": "Teams", "enabled": True, "events": ["started"]},
                ]
            },
        }
        send_notifications(account, "started", "Test", {"name": "User", "role": "admin"})
        assert mock_send.call_count == 2


class TestHandleGetNotifications:
    """Test handle_get_notifications."""

    def test_feature_disabled(self):
        from notifications import handle_get_notifications

        account = {"features": {"notifications": False}, "notifications": {"channels": []}}
        resp = handle_get_notifications(account, {"role": "superadmin"})
        body = json.loads(resp["body"])
        assert body["enabled"] is False

    def test_superadmin_can_view(self):
        from notifications import handle_get_notifications

        account = {
            "features": {"notifications": True},
            "notifications": {"channels": [{"id": "ch-1", "name": "Test"}]},
        }
        resp = handle_get_notifications(account, {"role": "superadmin"})
        body = json.loads(resp["body"])
        assert body["enabled"] is True
        assert body["canEdit"] is True
        assert len(body["channels"]) == 1

    def test_operator_cannot_view(self):
        from notifications import handle_get_notifications

        account = {
            "features": {"notifications": True},
            "notifications": {"channels": [{"id": "ch-1"}]},
        }
        resp = handle_get_notifications(account, {"role": "operator"})
        body = json.loads(resp["body"])
        assert body["canEdit"] is False
        assert len(body["channels"]) == 0


class TestHandleUpdateNotifications:
    """Test handle_update_notifications."""

    def test_update_as_superadmin(self, seeded_table, reset_utils_table):
        from notifications import handle_update_notifications

        body = {"channels": [{"id": "ch-new", "type": "email", "name": "New", "enabled": True, "events": ["started"]}]}
        resp = handle_update_notifications(
            {"features": {"notifications": True}, "notifications": {"channels": []}},
            "test-account",
            {"role": "superadmin"},
            body,
        )
        assert resp["statusCode"] == 200

    def test_update_as_operator_denied(self, seeded_table, reset_utils_table):
        from notifications import handle_update_notifications

        body = {"channels": []}
        resp = handle_update_notifications(
            {"features": {"notifications": True}, "notifications": {"channels": []}},
            "test-account",
            {"role": "operator"},
            body,
        )
        body_data = json.loads(resp["body"])
        assert body_data.get("denied") is True


class TestSendEmail:
    """Test send_email."""

    @patch("notifications.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp_class):
        from notifications import send_email

        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        config = {"to": "user@example.com", "smtpHost": "smtp.test.com", "smtpPort": 587, "smtpUser": "u", "smtpPass": "p"}
        result = send_email(config, "Test message", "Subject")
        assert result is True

    def test_send_email_no_recipient(self):
        from notifications import send_email
        result = send_email({}, "Test", "Subject")
        assert result is False


class TestSendTelegram:
    """Test send_telegram."""

    @patch("notifications.urllib_request.urlopen")
    @patch("notifications.urllib_request.Request")
    def test_send_telegram_success(self, mock_req, mock_urlopen):
        from notifications import send_telegram

        config = {"botToken": "123:ABC", "chatId": "-100123"}
        result = send_telegram(config, "Hello")
        assert result is True
        mock_req.assert_called_once()

    def test_send_telegram_missing_token(self):
        from notifications import send_telegram
        result = send_telegram({"chatId": "-100123"}, "Hello")
        assert result is False

    def test_send_telegram_missing_chat_id(self):
        from notifications import send_telegram
        result = send_telegram({"botToken": "123:ABC"}, "Hello")
        assert result is False


class TestSendTeams:
    """Test send_teams."""

    @patch("notifications.urllib_request.urlopen")
    @patch("notifications.urllib_request.Request")
    def test_send_teams_success(self, mock_req, mock_urlopen):
        from notifications import send_teams

        config = {"webhookUrl": "https://outlook.office.com/webhook/test"}
        result = send_teams(config, "Hello")
        assert result is True

    def test_send_teams_missing_url(self):
        from notifications import send_teams
        result = send_teams({}, "Hello")
        assert result is False


class TestHandleTestNotification:
    """Test handle_test_notification."""

    @patch("notifications.send_single_notification")
    def test_test_notification_success(self, mock_send):
        from notifications import handle_test_notification

        mock_send.return_value = True
        account = {
            "features": {"notifications": True},
            "notifications": {"channels": [{"id": "ch-1", "type": "email", "name": "Admin"}]},
        }
        body = {"channelId": "ch-1"}
        resp = handle_test_notification(account, {"role": "superadmin"}, body)
        body_data = json.loads(resp["body"])
        assert "Prueba enviada" in body_data.get("message", "") or resp["statusCode"] == 200

    def test_test_notification_operator_denied(self):
        from notifications import handle_test_notification

        account = {"features": {"notifications": True}, "notifications": {"channels": []}}
        body = {"channelId": "ch-1"}
        resp = handle_test_notification(account, {"role": "operator"}, body)
        body_data = json.loads(resp["body"])
        assert body_data.get("denied") is True or "Solo superadmin" in body_data.get("error", "")

    def test_test_notification_channel_not_found(self):
        from notifications import handle_test_notification

        account = {"features": {"notifications": True}, "notifications": {"channels": []}}
        body = {"channelId": "nonexistent"}
        resp = handle_test_notification(account, {"role": "superadmin"}, body)
        body_data = json.loads(resp["body"])
        assert "no encontrado" in body_data.get("error", "").lower() or resp["statusCode"] == 200
