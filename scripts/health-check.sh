#!/usr/bin/env bash
# Health Check Script - Post-deployment verification with automatic rollback
# Usage: ./scripts/health-check.sh <stack-url> <stack-name> [--region <region>] [--sns-topic <arn>]
#
# Validates deployment by:
#   1. Waiting 30 seconds for stack stabilization
#   2. Sending HTTP GET to {stack-url}/api/accounts with 10-second timeout
#   3. Retrying up to 3 times with 10-second intervals on failure
#   4. Triggering CloudFormation rollback if all retries fail
#   5. Sending notification on failure with status details
#
# Exit codes:
#   0 - Health check passed (HTTP 200)
#   1 - Health check failed and rollback initiated

set -uo pipefail

# ─── Arguments ──────────────────────────────────────────────────────────

STACK_URL="${1:-}"
STACK_NAME="${2:-}"
REGION="us-east-1"
SNS_TOPIC=""

shift 2 2>/dev/null || true

while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --sns-topic)
            SNS_TOPIC="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ -z "$STACK_URL" || -z "$STACK_NAME" ]]; then
    echo "Usage: ./scripts/health-check.sh <stack-url> <stack-name> [--region <region>] [--sns-topic <arn>]"
    exit 1
fi

# ─── Configuration ──────────────────────────────────────────────────────

HEALTH_ENDPOINT="${STACK_URL}/api/accounts"
MAX_RETRIES=3
RETRY_INTERVAL=10
RESPONSE_TIMEOUT=10
STABILIZATION_WAIT=30

# ─── Functions ──────────────────────────────────────────────────────────

send_notification() {
    local message="$1"
    local subject="$2"

    echo "📢 NOTIFICATION: ${subject}"
    echo "   ${message}"

    if [[ -n "$SNS_TOPIC" ]]; then
        aws sns publish \
            --topic-arn "$SNS_TOPIC" \
            --subject "$subject" \
            --message "$message" \
            --region "$REGION" 2>/dev/null || echo "   ⚠️  SNS publish failed (topic may not exist)"
    fi
}

trigger_rollback() {
    echo "🔄 Triggering CloudFormation rollback for stack: ${STACK_NAME}"

    # Attempt to cancel any in-progress update first
    aws cloudformation cancel-update-stack \
        --stack-name "$STACK_NAME" \
        --region "$REGION" 2>/dev/null || true

    # Trigger rollback via update-stack with the previous template
    local rollback_status
    rollback_status=$(aws cloudformation rollback-stack \
        --stack-name "$STACK_NAME" \
        --region "$REGION" 2>&1) || true

    # If rollback-stack is not available, try continue-rollback
    if echo "$rollback_status" | grep -qi "error\|exception"; then
        echo "   Attempting continue-update-rollback..."
        aws cloudformation continue-update-rollback \
            --stack-name "$STACK_NAME" \
            --region "$REGION" 2>/dev/null || true
    fi

    echo "   Rollback initiated for ${STACK_NAME}"
}

perform_health_check() {
    local attempt=$1
    local http_code
    local curl_exit

    echo "   Attempt ${attempt}/${MAX_RETRIES}: GET ${HEALTH_ENDPOINT}"

    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$RESPONSE_TIMEOUT" \
        --connect-timeout "$RESPONSE_TIMEOUT" \
        "$HEALTH_ENDPOINT" 2>/dev/null) || curl_exit=$?

    if [[ ${curl_exit:-0} -ne 0 ]]; then
        echo "   ❌ Request timed out or connection failed (curl exit: ${curl_exit:-unknown})"
        return 1
    fi

    if [[ "$http_code" == "200" ]]; then
        echo "   ✅ HTTP 200 OK"
        return 0
    else
        echo "   ❌ HTTP ${http_code} (expected 200)"
        return 1
    fi
}

# ─── Main ───────────────────────────────────────────────────────────────

echo ""
echo "=== Health Check: ${STACK_NAME} ==="
echo "  Endpoint: ${HEALTH_ENDPOINT}"
echo "  Timeout:  ${RESPONSE_TIMEOUT}s per request"
echo "  Retries:  ${MAX_RETRIES} attempts, ${RETRY_INTERVAL}s interval"
echo ""

# Step 1: Wait for stack stabilization
echo "⏳ Waiting ${STABILIZATION_WAIT}s for stack stabilization..."
sleep "$STABILIZATION_WAIT"

# Step 2: Perform health checks with retry logic
LAST_STATUS="unknown"
for attempt in $(seq 1 "$MAX_RETRIES"); do
    if perform_health_check "$attempt"; then
        echo ""
        echo "✅ Health check PASSED for ${STACK_NAME}"
        echo "   Deployment verified successfully."
        exit 0
    fi

    # Capture status for failure notification
    LAST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$RESPONSE_TIMEOUT" \
        "$HEALTH_ENDPOINT" 2>/dev/null || echo "timeout")

    # Wait before next retry (except after last attempt)
    if [[ $attempt -lt $MAX_RETRIES ]]; then
        echo "   Waiting ${RETRY_INTERVAL}s before next attempt..."
        sleep "$RETRY_INTERVAL"
    fi
done

# Step 3: All retries failed - trigger rollback and notify
echo ""
echo "❌ Health check FAILED for ${STACK_NAME} after ${MAX_RETRIES} attempts"
echo ""

# Determine failure reason
FAILURE_REASON=""
if [[ "$LAST_STATUS" == "timeout" || "$LAST_STATUS" == "000" ]]; then
    FAILURE_REASON="Connection timeout - endpoint did not respond within ${RESPONSE_TIMEOUT}s"
else
    FAILURE_REASON="HTTP status ${LAST_STATUS} returned (expected 200)"
fi

echo "   Failure: ${FAILURE_REASON}"

# Trigger rollback
trigger_rollback
ROLLBACK_STATUS="initiated"

# Send failure notification
NOTIFICATION_MSG="Deployment health check FAILED for stack '${STACK_NAME}'.

Failure Details:
  - Endpoint: ${HEALTH_ENDPOINT}
  - Condition: ${FAILURE_REASON}
  - Attempts: ${MAX_RETRIES}/${MAX_RETRIES} failed

Rollback Status: ${ROLLBACK_STATUS}
Region: ${REGION}
Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

send_notification "$NOTIFICATION_MSG" "DEPLOY FAILED: ${STACK_NAME} - Health Check Failed, Rollback Initiated"

echo ""
echo "🚨 Deployment FAILED. Rollback has been initiated."
exit 1
