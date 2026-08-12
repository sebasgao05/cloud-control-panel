"""Tests for backend/validators.py - Pydantic validation models."""

import pytest
from pydantic import ValidationError


class TestCreateAccountRequest:
    """Test CreateAccountRequest validation."""

    def test_valid_account(self):
        from validators import CreateAccountRequest
        data = {"id": "my-account", "name": "My Account", "region": "us-east-1"}
        validated = CreateAccountRequest.model_validate(data)
        assert validated.id == "my-account"
        assert validated.name == "My Account"

    def test_invalid_id_special_chars(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "inv@lid!", "name": "X"})

    def test_id_too_long(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "a" * 51, "name": "X"})

    def test_empty_id(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "", "name": "X"})

    def test_missing_name(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "valid"})

    def test_invalid_region(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "acc", "name": "X", "region": "invalid"})

    def test_valid_role_arn(self):
        from validators import CreateAccountRequest
        data = {
            "id": "acc",
            "name": "X",
            "crossAccountRoleArn": "arn:aws:iam::123456789012:role/MyRole",
        }
        validated = CreateAccountRequest.model_validate(data)
        assert validated.crossAccountRoleArn is not None

    def test_invalid_role_arn(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "acc", "name": "X", "crossAccountRoleArn": "not-an-arn"})

    def test_invalid_aws_account_id(self):
        from validators import CreateAccountRequest
        with pytest.raises(ValidationError):
            CreateAccountRequest.model_validate({"id": "acc", "name": "X", "awsAccountId": "12345"})

    def test_valid_aws_account_id(self):
        from validators import CreateAccountRequest
        data = {"id": "acc", "name": "X", "awsAccountId": "123456789012"}
        validated = CreateAccountRequest.model_validate(data)
        assert validated.awsAccountId == "123456789012"


class TestCreateInstanceRequest:
    """Test CreateInstanceRequest validation."""

    def test_valid_instance(self):
        from validators import CreateInstanceRequest
        data = {"id": "my-inst", "name": "My Instance", "instanceId": "i-0abcdef1234567890"}
        validated = CreateInstanceRequest.model_validate(data)
        assert validated.id == "my-inst"
        assert validated.instanceId == "i-0abcdef1234567890"

    def test_invalid_instance_id_format(self):
        from validators import CreateInstanceRequest
        with pytest.raises(ValidationError):
            CreateInstanceRequest.model_validate({"id": "x", "name": "X", "instanceId": "invalid"})

    def test_invalid_instance_id_too_short(self):
        from validators import CreateInstanceRequest
        with pytest.raises(ValidationError):
            CreateInstanceRequest.model_validate({"id": "x", "name": "X", "instanceId": "i-123"})

    def test_valid_dashboard_port(self):
        from validators import CreateInstanceRequest
        data = {"id": "x", "name": "X", "instanceId": "i-0abcdef1234567890", "dashboardPort": 8080}
        validated = CreateInstanceRequest.model_validate(data)
        assert validated.dashboardPort == 8080

    def test_invalid_dashboard_port_too_high(self):
        from validators import CreateInstanceRequest
        with pytest.raises(ValidationError):
            CreateInstanceRequest.model_validate(
                {"id": "x", "name": "X", "instanceId": "i-0abcdef1234567890", "dashboardPort": 99999}
            )

    def test_invalid_group_ref(self):
        from validators import CreateInstanceRequest
        with pytest.raises(ValidationError):
            CreateInstanceRequest.model_validate(
                {"id": "x", "name": "X", "instanceId": "i-0abcdef1234567890", "group": "inv@lid!"}
            )


class TestCreateGroupRequest:
    """Test CreateGroupRequest validation."""

    def test_valid_group(self):
        from validators import CreateGroupRequest
        data = {"id": "grp-1", "name": "My Group", "color": "#FF0000"}
        validated = CreateGroupRequest.model_validate(data)
        assert validated.color == "#FF0000"

    def test_invalid_color(self):
        from validators import CreateGroupRequest
        with pytest.raises(ValidationError):
            CreateGroupRequest.model_validate({"id": "grp", "name": "G", "color": "red"})

    def test_valid_hex_color(self):
        from validators import CreateGroupRequest
        data = {"id": "grp", "name": "G", "color": "#6366f1"}
        validated = CreateGroupRequest.model_validate(data)
        assert validated.color == "#6366f1"


class TestCreateKeyRequest:
    """Test CreateKeyRequest validation."""

    def test_valid_key(self):
        from validators import CreateKeyRequest
        data = {"name": "My Key", "role": "operator", "accounts": ["acc-1"]}
        validated = CreateKeyRequest.model_validate(data)
        assert validated.name == "My Key"
        assert validated.role == "operator"

    def test_invalid_role(self):
        from validators import CreateKeyRequest
        with pytest.raises(ValidationError):
            CreateKeyRequest.model_validate({"name": "X", "role": "superadmin", "accounts": []})

    def test_wildcard_account(self):
        from validators import CreateKeyRequest
        data = {"name": "X", "role": "admin", "accounts": ["*"]}
        validated = CreateKeyRequest.model_validate(data)
        assert validated.accounts == ["*"]

    def test_invalid_account_in_list(self):
        from validators import CreateKeyRequest
        with pytest.raises(ValidationError):
            CreateKeyRequest.model_validate({"name": "X", "role": "operator", "accounts": ["inv@lid!"]})


class TestUpdateKeyAccountsRequest:
    """Test UpdateKeyAccountsRequest validation."""

    def test_valid_update(self):
        from validators import UpdateKeyAccountsRequest
        data = {"accounts": ["acc-1", "acc-2", "*"]}
        validated = UpdateKeyAccountsRequest.model_validate(data)
        assert len(validated.accounts) == 3

    def test_invalid_account_id(self):
        from validators import UpdateKeyAccountsRequest
        with pytest.raises(ValidationError):
            UpdateKeyAccountsRequest.model_validate({"accounts": ["good", "b@d"]})


class TestScheduleRule:
    """Test ScheduleRule validation."""

    def test_valid_cron(self):
        from validators import ScheduleRule
        data = {"id": "rule-1", "startCron": "0 7 * * 1-5", "stopCron": "0 20 * * 1-5", "instances": ["i1"]}
        validated = ScheduleRule.model_validate(data)
        assert validated.startCron == "0 7 * * 1-5"

    def test_invalid_cron(self):
        from validators import ScheduleRule
        with pytest.raises(ValidationError):
            ScheduleRule.model_validate({"startCron": "not a cron"})

    def test_valid_cron_with_ranges(self):
        from validators import ScheduleRule
        data = {"startCron": "30 6 * * 0,6"}
        validated = ScheduleRule.model_validate(data)
        assert validated.startCron == "30 6 * * 0,6"


class TestUpdateScheduleRequest:
    """Test UpdateScheduleRequest validation."""

    def test_valid_schedule(self):
        from validators import UpdateScheduleRequest
        data = {
            "timezone": "America/Bogota",
            "rules": [{"id": "r1", "startCron": "0 7 * * 1-5", "instances": ["i1"], "enabled": True}],
        }
        validated = UpdateScheduleRequest.model_validate(data)
        assert validated.timezone == "America/Bogota"
        assert len(validated.rules) == 1


class TestNotificationModels:
    """Test notification validation models."""

    def test_valid_email_channel(self):
        from validators import NotificationChannelConfig
        data = {"to": "user@example.com", "smtpHost": "smtp.example.com", "smtpPort": 587}
        validated = NotificationChannelConfig.model_validate(data)
        assert validated.to == "user@example.com"

    def test_invalid_email(self):
        from validators import NotificationChannelConfig
        with pytest.raises(ValidationError):
            NotificationChannelConfig.model_validate({"to": "not-an-email"})

    def test_valid_webhook_url(self):
        from validators import NotificationChannelConfig
        data = {"webhookUrl": "https://outlook.office.com/webhook/example"}
        validated = NotificationChannelConfig.model_validate(data)
        assert validated.webhookUrl is not None

    def test_invalid_webhook_url(self):
        from validators import NotificationChannelConfig
        with pytest.raises(ValidationError):
            NotificationChannelConfig.model_validate({"webhookUrl": "http://not-https.com"})

    def test_update_notifications_request(self):
        from validators import UpdateNotificationsRequest
        data = {"channels": [{"id": "ch-1", "type": "email", "name": "Test", "enabled": True, "events": ["started"]}]}
        validated = UpdateNotificationsRequest.model_validate(data)
        assert len(validated.channels) == 1

    def test_test_notification_request(self):
        from validators import TestNotificationRequest
        data = {"channelId": "ch-1"}
        validated = TestNotificationRequest.model_validate(data)
        assert validated.channelId == "ch-1"

    def test_test_notification_empty_id(self):
        from validators import TestNotificationRequest
        with pytest.raises(ValidationError):
            TestNotificationRequest.model_validate({"channelId": ""})


class TestValidatePathParameter:
    """Test validate_path_parameter."""

    def test_valid_ids(self):
        from validators import validate_path_parameter
        assert validate_path_parameter("my-account") is True
        assert validate_path_parameter("acc_123") is True
        assert validate_path_parameter("a") is True

    def test_invalid_ids(self):
        from validators import validate_path_parameter
        assert validate_path_parameter("") is False
        assert validate_path_parameter("a" * 51) is False
        assert validate_path_parameter("-starts-dash") is False
        assert validate_path_parameter("has space") is False
        assert validate_path_parameter("has@special") is False


class TestFormatValidationErrors:
    """Test format_validation_errors."""

    def test_formats_errors(self):
        from validators import CreateAccountRequest, format_validation_errors
        try:
            CreateAccountRequest.model_validate({"id": "", "name": ""})
            assert False, "Should have raised"
        except ValidationError as e:
            errors = format_validation_errors(e)
            assert len(errors) >= 1
            assert "field" in errors[0]
            assert "message" in errors[0]
            assert "type" in errors[0]


class TestImportConfigRequest:
    """Test ImportConfigRequest validation."""

    def test_valid_import(self):
        from validators import ImportConfigRequest
        data = {"settings": {"region": "us-east-1"}, "apiKeys": {}, "accounts": []}
        validated = ImportConfigRequest.model_validate(data)
        assert validated.settings is not None

    def test_minimal_import(self):
        from validators import ImportConfigRequest
        data = {}
        validated = ImportConfigRequest.model_validate(data)
        assert validated.accounts == []
