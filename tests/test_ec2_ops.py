"""Tests for backend/ec2_ops.py - EC2 operations and instance/group handlers."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestGetEc2Client:
    """Test get_ec2_client with and without cross-account role."""

    @patch("ec2_ops.boto3.client")
    def test_direct_client(self, mock_client):
        from ec2_ops import get_ec2_client
        account = {"region": "us-east-1"}
        get_ec2_client(account)
        mock_client.assert_called_with("ec2", region_name="us-east-1")

    @patch("ec2_ops.boto3.client")
    def test_cross_account_role(self, mock_client):
        from ec2_ops import get_ec2_client

        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }
        mock_client.side_effect = lambda svc, **kwargs: mock_sts if svc == "sts" else MagicMock()

        account = {"region": "eu-west-1", "crossAccountRoleArn": "arn:aws:iam::123456789012:role/TestRole"}
        get_ec2_client(account)
        mock_sts.assume_role.assert_called_once()


class TestHandleListInstances:
    """Test handle_list_instances."""

    @patch("ec2_ops.get_ec2_client")
    def test_list_instances_running(self, mock_get_ec2):
        from ec2_ops import handle_list_instances

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-0abcdef1234567890",
                            "State": {"Name": "running"},
                            "PublicIpAddress": "54.100.1.1",
                            "LaunchTime": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
                        }
                    ]
                }
            ]
        }
        mock_get_ec2.return_value = mock_ec2

        account = {
            "id": "test-acc",
            "name": "Test",
            "instances": [{"id": "i1", "name": "Inst 1", "instanceId": "i-0abcdef1234567890", "group": None}],
            "groups": [],
        }
        resp = handle_list_instances(account)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["instances"]) == 1
        assert body["instances"][0]["state"] == "running"
        assert body["instances"][0]["publicIp"] == "54.100.1.1"

    @patch("ec2_ops.get_ec2_client")
    def test_list_instances_stopped(self, mock_get_ec2):
        from ec2_ops import handle_list_instances

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {"Instances": [{"InstanceId": "i-0abcdef1234567890", "State": {"Name": "stopped"}}]}
            ]
        }
        mock_get_ec2.return_value = mock_ec2

        account = {
            "id": "test-acc",
            "name": "Test",
            "instances": [{"id": "i1", "name": "Inst 1", "instanceId": "i-0abcdef1234567890", "group": None}],
            "groups": [],
        }
        resp = handle_list_instances(account)
        body = json.loads(resp["body"])
        assert body["instances"][0]["state"] == "stopped"
        assert body["instances"][0]["publicIp"] is None

    @patch("ec2_ops.get_ec2_client")
    def test_list_instances_ec2_error(self, mock_get_ec2):
        from ec2_ops import handle_list_instances

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.side_effect = Exception("AWS Error")
        mock_get_ec2.return_value = mock_ec2

        account = {
            "id": "test-acc",
            "name": "Test",
            "instances": [{"id": "i1", "name": "Inst 1", "instanceId": "i-0abcdef1234567890", "group": None}],
            "groups": [],
        }
        resp = handle_list_instances(account)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        # Should still return instances with "unknown" state
        assert body["instances"][0]["state"] == "unknown"


class TestHandleInstanceStatus:
    """Test handle_instance_status."""

    @patch("ec2_ops.get_ec2_client")
    def test_instance_status(self, mock_get_ec2):
        from ec2_ops import handle_instance_status

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-0abcdef1234567890",
                            "State": {"Name": "running"},
                            "PublicIpAddress": "54.100.1.1",
                            "LaunchTime": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
                        }
                    ]
                }
            ]
        }
        mock_get_ec2.return_value = mock_ec2

        account = {"region": "us-east-1"}
        instance = {"id": "i1", "name": "Test", "instanceId": "i-0abcdef1234567890"}
        resp = handle_instance_status(account, instance)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["state"] == "running"


class TestHandleInstanceStartStop:
    """Test handle_instance_start and handle_instance_stop."""

    @patch("notifications.send_notifications")
    @patch("scheduler.log_activity")
    @patch("ec2_ops.get_ec2_client")
    def test_start_instance(self, mock_get_ec2, mock_log, mock_notify):
        from ec2_ops import handle_instance_start

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        account = {"id": "acc-1", "region": "us-east-1"}
        instance = {"id": "i1", "name": "Test", "instanceId": "i-0abcdef1234567890"}
        user_info = {"name": "Operator"}

        resp = handle_instance_start(account, instance, user_info)
        assert resp["statusCode"] == 200
        mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-0abcdef1234567890"])
        mock_log.assert_called_once()
        mock_notify.assert_called_once()

    @patch("notifications.send_notifications")
    @patch("scheduler.log_activity")
    @patch("ec2_ops.get_ec2_client")
    def test_stop_instance(self, mock_get_ec2, mock_log, mock_notify):
        from ec2_ops import handle_instance_stop

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        account = {"id": "acc-1", "region": "us-east-1"}
        instance = {"id": "i1", "name": "Test", "instanceId": "i-0abcdef1234567890"}
        user_info = {"name": "Operator"}

        resp = handle_instance_stop(account, instance, user_info)
        assert resp["statusCode"] == 200
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-0abcdef1234567890"])


class TestHandleGroupStartStop:
    """Test handle_group_start and handle_group_stop."""

    @patch("notifications.send_notifications")
    @patch("ec2_ops.get_ec2_client")
    def test_group_start(self, mock_get_ec2, mock_notify):
        from ec2_ops import handle_group_start

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "instances": [
                {"id": "i1", "name": "Inst 1", "instanceId": "i-001"},
                {"id": "i2", "name": "Inst 2", "instanceId": "i-002"},
            ],
            "groups": [],
        }
        group = {"id": "grp-1", "name": "Test Group", "startOrder": ["i1", "i2"]}
        user_info = {"name": "Admin"}

        resp = handle_group_start(account, group, user_info)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["started"]) == 2
        assert mock_ec2.start_instances.call_count == 2

    @patch("notifications.send_notifications")
    @patch("ec2_ops.get_ec2_client")
    def test_group_stop(self, mock_get_ec2, mock_notify):
        from ec2_ops import handle_group_stop

        mock_ec2 = MagicMock()
        mock_get_ec2.return_value = mock_ec2

        account = {
            "id": "acc-1",
            "region": "us-east-1",
            "instances": [
                {"id": "i1", "name": "Inst 1", "instanceId": "i-001"},
                {"id": "i2", "name": "Inst 2", "instanceId": "i-002"},
            ],
            "groups": [],
        }
        group = {"id": "grp-1", "name": "Test Group", "stopOrder": ["i2", "i1"]}
        user_info = {"name": "Admin"}

        resp = handle_group_stop(account, group, user_info)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["stopped"]) == 2
        assert mock_ec2.stop_instances.call_count == 2


class TestHandleDashboardUrl:
    """Test handle_dashboard_url."""

    @patch("ec2_ops.get_ec2_client")
    def test_dashboard_with_port_and_ip(self, mock_get_ec2):
        from ec2_ops import handle_dashboard_url

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [{"PublicIpAddress": "54.100.1.1"}]}]
        }
        mock_get_ec2.return_value = mock_ec2

        account = {"region": "us-east-1"}
        instance = {"id": "i1", "instanceId": "i-001", "dashboardPort": 8080}
        resp = handle_dashboard_url(account, instance)
        body = json.loads(resp["body"])
        assert body["url"] == "http://54.100.1.1:8080"

    def test_dashboard_no_port(self):
        from ec2_ops import handle_dashboard_url

        account = {"region": "us-east-1"}
        instance = {"id": "i1", "instanceId": "i-001", "dashboardPort": None}
        resp = handle_dashboard_url(account, instance)
        body = json.loads(resp["body"])
        assert body["url"] is None
        assert "No dashboard" in body["reason"]


class TestHandleListAccounts:
    """Test handle_list_accounts."""

    def test_list_accounts(self):
        from ec2_ops import handle_list_accounts

        user_info = {"name": "Admin", "role": "admin", "accounts": ["*"]}
        config = {
            "accounts": [
                {"id": "acc-1", "name": "Account 1", "awsAccountId": "111111111111", "region": "us-east-1", "instances": [1, 2], "groups": [1]},
            ]
        }
        resp = handle_list_accounts(user_info, config)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["accounts"]) == 1
        assert body["accounts"][0]["instanceCount"] == 2
        assert body["accounts"][0]["groupCount"] == 1
