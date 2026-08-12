"""
Shared test fixtures for the Cloud Control Panel backend test suite.
"""

import os
import sys

import bcrypt
import boto3
import pytest
from moto import mock_aws

# Add backend to path so we can import modules directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Set environment variables before importing backend modules
os.environ["CONFIG_TABLE"] = "test-table"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"


# Test API key (plaintext) and its bcrypt hash
TEST_API_KEY = "test-key-plaintext-value"
TEST_API_KEY_HASH = bcrypt.hashpw(TEST_API_KEY.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
TEST_KEY_ID = "key-id-001"

TEST_ADMIN_KEY = "admin-key-plaintext"
TEST_ADMIN_KEY_HASH = bcrypt.hashpw(TEST_ADMIN_KEY.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
TEST_ADMIN_KEY_ID = "key-id-admin"

TEST_SUPERADMIN_KEY = "superadmin-key-plaintext"
TEST_SUPERADMIN_KEY_HASH = bcrypt.hashpw(TEST_SUPERADMIN_KEY.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
TEST_SUPERADMIN_KEY_ID = "key-id-superadmin"


@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table with test data."""
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


@pytest.fixture
def seeded_table(dynamodb_table):
    """DynamoDB table seeded with test config data."""
    table = dynamodb_table

    # Settings
    table.put_item(Item={
        "PK": "CONFIG",
        "SK": "SETTINGS",
        "data": {"defaultRegion": "us-east-1", "pollIntervalSeconds": 30, "timezone": "America/Bogota"},
    })

    # API keys (operator)
    table.put_item(Item={
        "PK": "CONFIG",
        "SK": f"APIKEY#{TEST_KEY_ID}",
        "data": {
            "hash": TEST_API_KEY_HASH,
            "name": "Test Operator",
            "role": "operator",
            "accounts": ["test-account"],
            "scheduler": {"view": True, "edit": False},
        },
    })

    # API keys (admin)
    table.put_item(Item={
        "PK": "CONFIG",
        "SK": f"APIKEY#{TEST_ADMIN_KEY_ID}",
        "data": {
            "hash": TEST_ADMIN_KEY_HASH,
            "name": "Test Admin",
            "role": "admin",
            "accounts": ["*"],
        },
    })

    # API keys (superadmin)
    table.put_item(Item={
        "PK": "CONFIG",
        "SK": f"APIKEY#{TEST_SUPERADMIN_KEY_ID}",
        "data": {
            "hash": TEST_SUPERADMIN_KEY_HASH,
            "name": "Test Superadmin",
            "role": "superadmin",
            "accounts": ["*"],
        },
    })

    # Account
    table.put_item(Item={
        "PK": "CONFIG",
        "SK": "ACCOUNT#test-account",
        "data": {
            "name": "Test Account",
            "awsAccountId": "123456789012",
            "region": "us-east-1",
            "features": {"scheduler": True, "notifications": True, "costEstimate": True},
        },
    })

    # Instance
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "INSTANCE#inst-1",
        "data": {
            "id": "inst-1",
            "name": "Test Instance",
            "instanceId": "i-0abcdef1234567890",
            "description": "A test instance",
            "dashboardPort": 8080,
            "group": "grp-1",
        },
    })

    # Second instance
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "INSTANCE#inst-2",
        "data": {
            "id": "inst-2",
            "name": "Test Instance 2",
            "instanceId": "i-0abcdef1234567891",
            "description": "Second test instance",
            "dashboardPort": None,
            "group": "grp-1",
        },
    })

    # Group
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "GROUP#grp-1",
        "data": {
            "id": "grp-1",
            "name": "Test Group",
            "description": "A test group",
            "color": "#6366f1",
            "startOrder": ["inst-1", "inst-2"],
            "stopOrder": ["inst-2", "inst-1"],
        },
    })

    # Schedule rule
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "SCHEDULE#rule-1",
        "data": {
            "id": "rule-1",
            "name": "Weekday schedule",
            "instances": ["inst-1", "inst-2"],
            "startCron": "0 7 * * 1-5",
            "stopCron": "0 20 * * 1-5",
            "enabled": True,
        },
    })

    # Notification channel
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "CHANNEL#ch-1",
        "data": {
            "id": "ch-1",
            "type": "email",
            "name": "Admin Email",
            "config": {"to": "admin@example.com", "smtpHost": "smtp.example.com", "smtpPort": 587},
            "events": ["started", "stopped", "error"],
            "enabled": True,
        },
    })

    # Disabled notification channel
    table.put_item(Item={
        "PK": "ACCOUNT#test-account",
        "SK": "CHANNEL#ch-2",
        "data": {
            "id": "ch-2",
            "type": "telegram",
            "name": "Telegram Channel",
            "config": {"botToken": "123:ABC", "chatId": "-100123"},
            "events": ["started", "stopped"],
            "enabled": False,
        },
    })

    yield table


@pytest.fixture
def reset_utils_table():
    """Reset the cached table in utils module between tests."""
    import utils
    utils._ddb = None
    utils._table = None
    yield
    utils._ddb = None
    utils._table = None


@pytest.fixture
def config_from_seeded(seeded_table, reset_utils_table):
    """Load config from seeded DynamoDB table."""
    import utils
    return utils.load_config_from_db()


@pytest.fixture
def operator_event():
    """Lambda event with operator API key."""
    return {
        "headers": {"x-api-key": TEST_API_KEY},
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/api/accounts",
    }


@pytest.fixture
def admin_event():
    """Lambda event with admin API key."""
    return {
        "headers": {"x-api-key": TEST_ADMIN_KEY},
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/api/accounts",
    }


@pytest.fixture
def superadmin_event():
    """Lambda event with superadmin API key."""
    return {
        "headers": {"x-api-key": TEST_SUPERADMIN_KEY},
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/api/accounts",
    }


@pytest.fixture
def operator_user_info():
    """User info dict for an operator."""
    return {
        "name": "Test Operator",
        "role": "operator",
        "accounts": ["test-account"],
        "scheduler": {"view": True, "edit": False},
    }


@pytest.fixture
def admin_user_info():
    """User info dict for an admin."""
    return {
        "name": "Test Admin",
        "role": "admin",
        "accounts": ["*"],
    }


@pytest.fixture
def superadmin_user_info():
    """User info dict for a superadmin."""
    return {
        "name": "Test Superadmin",
        "role": "superadmin",
        "accounts": ["*"],
    }


@pytest.fixture
def test_account():
    """A test account dict as would be returned by load_config_from_db."""
    return {
        "id": "test-account",
        "name": "Test Account",
        "awsAccountId": "123456789012",
        "region": "us-east-1",
        "features": {"scheduler": True, "notifications": True, "costEstimate": True},
        "instances": [
            {
                "id": "inst-1",
                "name": "Test Instance",
                "instanceId": "i-0abcdef1234567890",
                "description": "A test instance",
                "dashboardPort": 8080,
                "group": "grp-1",
            },
            {
                "id": "inst-2",
                "name": "Test Instance 2",
                "instanceId": "i-0abcdef1234567891",
                "description": "Second test instance",
                "dashboardPort": None,
                "group": "grp-1",
            },
        ],
        "groups": [
            {
                "id": "grp-1",
                "name": "Test Group",
                "description": "A test group",
                "color": "#6366f1",
                "startOrder": ["inst-1", "inst-2"],
                "stopOrder": ["inst-2", "inst-1"],
            },
        ],
        "schedule": {
            "timezone": "America/Bogota",
            "rules": [
                {
                    "id": "rule-1",
                    "name": "Weekday schedule",
                    "instances": ["inst-1", "inst-2"],
                    "startCron": "0 7 * * 1-5",
                    "stopCron": "0 20 * * 1-5",
                    "enabled": True,
                },
            ],
        },
        "notifications": {
            "channels": [
                {
                    "id": "ch-1",
                    "type": "email",
                    "name": "Admin Email",
                    "config": {"to": "admin@example.com", "smtpHost": "smtp.example.com", "smtpPort": 587},
                    "events": ["started", "stopped", "error"],
                    "enabled": True,
                },
                {
                    "id": "ch-2",
                    "type": "telegram",
                    "name": "Telegram Channel",
                    "config": {"botToken": "123:ABC", "chatId": "-100123"},
                    "events": ["started", "stopped"],
                    "enabled": False,
                },
            ],
        },
    }
