"""Integration tests against the mock server."""

import os
import subprocess
import sys
import time

import pytest
import requests

MOCK_SERVER_PORT = 18080
MOCK_SERVER_URL = f"http://localhost:{MOCK_SERVER_PORT}"
MOCK_API_KEY = "demo"  # Key from mock/server.py MOCK_CONFIG


def wait_for_server(url, timeout=10):
    """Wait for the mock server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(url, timeout=1)
            return True
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def mock_server():
    """Start the mock server in a subprocess for integration tests."""
    server_path = os.path.join(os.path.dirname(__file__), "..", "mock", "server.py")
    if not os.path.exists(server_path):
        pytest.skip("Mock server not found")

    proc = subprocess.Popen(
        [sys.executable, server_path, "--port", str(MOCK_SERVER_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    try:
        if not wait_for_server(MOCK_SERVER_URL):
            proc.terminate()
            proc.wait(timeout=5)
            pytest.skip("Mock server did not start in time")
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestIntegrationAuthentication:
    """Test authentication flow against mock server."""

    def test_no_key_returns_401(self, mock_server):
        resp = requests.get(f"{MOCK_SERVER_URL}/api/accounts")
        assert resp.status_code == 401

    def test_invalid_key_returns_401(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts",
            headers={"x-api-key": "invalid-key"},
        )
        assert resp.status_code == 401

    def test_valid_key_returns_200(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200


class TestIntegrationAccounts:
    """Test account operations against mock server."""

    def test_list_accounts(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accounts" in data
        assert len(data["accounts"]) >= 1

    def test_list_instances(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/instances",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "instances" in data
        assert len(data["instances"]) >= 1

    def test_access_denied_for_restricted_user(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/nuvu-10/instances",
            headers={"x-api-key": "sanidad-key"},
        )
        assert resp.status_code == 403


class TestIntegrationInstances:
    """Test instance operations against mock server."""

    def test_instance_status(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/instances/san-app/status",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert data["state"] in ("running", "stopped")

    def test_start_instance(self, mock_server):
        resp = requests.post(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/instances/san-app/start",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data

    def test_stop_instance(self, mock_server):
        resp = requests.post(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/instances/san-app/stop",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data

    def test_instance_not_found(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/instances/nonexistent/status",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 404


class TestIntegrationScheduler:
    """Test scheduler operations against mock server."""

    def test_get_schedule(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/schedule",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_update_schedule(self, mock_server):
        body = {
            "timezone": "America/Bogota",
            "rules": [
                {"id": "test-rule", "instances": ["san-app"], "startCron": "0 9 * * 1-5", "stopCron": "0 17 * * 1-5", "enabled": True}
            ],
        }
        resp = requests.put(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/schedule",
            headers={"x-api-key": MOCK_API_KEY, "Content-Type": "application/json"},
            json=body,
        )
        assert resp.status_code == 200


class TestIntegrationNotifications:
    """Test notification operations against mock server."""

    def test_get_notifications(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/notifications",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_update_notifications(self, mock_server):
        body = {
            "channels": [
                {"id": "ch-test", "type": "email", "name": "Test", "enabled": True, "events": ["started"],
                 "config": {"to": "test@example.com"}}
            ]
        }
        resp = requests.put(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/notifications",
            headers={"x-api-key": MOCK_API_KEY, "Content-Type": "application/json"},
            json=body,
        )
        assert resp.status_code == 200

    def test_test_notification(self, mock_server):
        # Use a channel that exists in the initial mock config
        # First get the current channels to find a valid ID
        get_resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/notifications",
            headers={"x-api-key": MOCK_API_KEY},
        )
        data = get_resp.json()
        channels = data.get("channels", [])
        if not channels:
            pytest.skip("No channels available in mock server")
        channel_id = channels[0]["id"]

        body = {"channelId": channel_id}
        resp = requests.post(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/notifications/test",
            headers={"x-api-key": MOCK_API_KEY, "Content-Type": "application/json"},
            json=body,
        )
        assert resp.status_code == 200


class TestIntegrationGroups:
    """Test group operations against mock server."""

    def test_group_status(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/groups/sanidad-core/status",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data

    def test_group_start(self, mock_server):
        resp = requests.post(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/groups/sanidad-core/start",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200

    def test_group_stop(self, mock_server):
        resp = requests.post(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/groups/sanidad-core/stop",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200


class TestIntegrationCosts:
    """Test cost estimation via mock server."""

    def test_get_costs(self, mock_server):
        resp = requests.get(
            f"{MOCK_SERVER_URL}/api/accounts/sanidad/costs",
            headers={"x-api-key": MOCK_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
