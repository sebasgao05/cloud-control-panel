"""Tests for the health-check.sh script structure and correctness.

Validates that the health check script:
- Exists and is properly structured
- Contains the required logic per Requirements 12.1-12.5
- Uses correct retry configuration (3 attempts, 10s intervals)
- Includes the 30-second stabilization wait
- Triggers CloudFormation rollback on failure
- Sends notifications with failure details
"""

import os
import subprocess

import pytest


SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scripts", "health-check.sh"
)


def read_script():
    """Read the health check script with UTF-8 encoding."""
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        return f.read()


class TestHealthCheckScriptStructure:
    """Verify the health check script exists and has correct structure."""

    def test_script_exists(self):
        """Script file must exist at scripts/health-check.sh."""
        assert os.path.isfile(SCRIPT_PATH), f"Script not found at {SCRIPT_PATH}"

    def test_script_has_shebang(self):
        """Script must start with a proper bash shebang."""
        with open(SCRIPT_PATH, encoding="utf-8") as f:
            first_line = f.readline().strip()
        assert first_line == "#!/usr/bin/env bash"

    def test_script_content_has_stabilization_wait(self):
        """Req 12.1: Script must include a 30-second stabilization wait."""
        content = read_script()
        assert "STABILIZATION_WAIT=30" in content or "sleep 30" in content

    def test_script_content_has_response_timeout(self):
        """Req 12.1: Script must use 10-second response timeout for curl."""
        content = read_script()
        assert "RESPONSE_TIMEOUT=10" in content or "--max-time" in content

    def test_script_content_has_health_endpoint(self):
        """Req 12.1: Script must target /api/health endpoint."""
        content = read_script()
        assert "/api/health" in content

    def test_script_content_has_retry_logic(self):
        """Req 12.2: Script must retry up to 3 times."""
        content = read_script()
        assert "MAX_RETRIES=3" in content

    def test_script_content_has_retry_interval(self):
        """Req 12.2: Script must wait 10 seconds between retry attempts."""
        content = read_script()
        assert "RETRY_INTERVAL=10" in content

    def test_script_content_has_rollback_logic(self):
        """Req 12.3: Script must trigger CloudFormation rollback on failure."""
        content = read_script()
        assert "cloudformation" in content.lower()
        assert "rollback" in content.lower()

    def test_script_content_has_notification_logic(self):
        """Req 12.4: Script must send notification on failure."""
        content = read_script()
        assert "send_notification" in content or "sns" in content.lower()

    def test_script_content_has_failure_details_in_notification(self):
        """Req 12.4: Notification must include HTTP status/timeout info."""
        content = read_script()
        # Check for HTTP status reporting
        assert "http_code" in content.lower() or "status" in content.lower()
        assert "timeout" in content.lower()

    def test_script_content_has_success_exit_code(self):
        """Req 12.5: Script must exit 0 on success."""
        content = read_script()
        assert "exit 0" in content

    def test_script_content_has_failure_exit_code(self):
        """Script must exit with non-zero code on failure."""
        content = read_script()
        assert "exit 1" in content

    def test_script_accepts_stack_url_parameter(self):
        """Script must accept stack URL as first parameter."""
        content = read_script()
        assert "STACK_URL" in content

    def test_script_accepts_stack_name_parameter(self):
        """Script must accept stack name as second parameter."""
        content = read_script()
        assert "STACK_NAME" in content

    def test_script_checks_http_200(self):
        """Req 12.5: Script must check for HTTP 200 status code."""
        content = read_script()
        assert '"200"' in content or "'200'" in content

    def test_script_uses_curl_for_http_request(self):
        """Script must use curl for HTTP GET requests."""
        content = read_script()
        assert "curl" in content


class TestHealthCheckScriptExecution:
    """Test script execution with missing arguments."""

    def test_script_shows_usage_on_missing_args(self):
        """Script should show usage and exit 1 when called without args."""
        # Only run if bash is available (Linux/CI environments)
        if os.name == "nt":
            pytest.skip("Bash execution tests require Linux/macOS")

        result = subprocess.run(
            ["bash", SCRIPT_PATH],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 1
        assert "Usage" in result.stdout or "usage" in result.stdout.lower()
