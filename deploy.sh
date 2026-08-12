#!/usr/bin/env bash
# Cloud Control Panel - Deploy Script (Multi-account version)
# Usage: ./deploy.sh [--stack-tag ccp-main] [--region us-east-1] [--env prod]
# Prerequisites: AWS CLI configured with principal account

set -euo pipefail

# Defaults
STACK_TAG="ccp-main"
REGION="us-east-1"
ENV="prod"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-tag)
            STACK_TAG="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./deploy.sh [--stack-tag TAG] [--region REGION] [--env ENV]"
            echo ""
            echo "Options:"
            echo "  --stack-tag   Stack tag for naming (default: ccp-main)"
            echo "  --region      AWS region (default: us-east-1)"
            echo "  --env         Environment: prod, staging (default: prod)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

STACK_NAME="cloud-control-${STACK_TAG}"
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
S3_BUCKET="cloud-control-deploy-${ACCOUNT_ID}"

echo ""
echo "=== Cloud Control Panel Deploy (Multi-account) ==="
echo "  Stack: ${STACK_NAME}"
echo "  Account: ${ACCOUNT_ID}"
echo "  Region: ${REGION}"
echo "  Environment: ${ENV}"
echo ""

# Step 1: Create deployment bucket if needed
echo "[1/6] Checking deploy bucket..."
if ! aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
    echo "  Creating bucket: ${S3_BUCKET}"
    aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}" > /dev/null
fi
echo "  OK"

# Step 2: Copy accounts.json to backend (bundled with Lambda)
echo "[2/6] Bundling config with Lambda..."
cp config/accounts.json backend/accounts.json
echo "  OK"

# Step 3: Package CloudFormation
echo "[3/6] Packaging CloudFormation template..."
mkdir -p .aws-sam
aws cloudformation package \
    --template-file template.yaml \
    --s3-bucket "${S3_BUCKET}" \
    --s3-prefix cfn \
    --output-template-file .aws-sam/packaged.yaml \
    --region "${REGION}" > /dev/null
echo "  OK"

# Step 4: Deploy stack
echo "[4/6] Deploying stack (3-5 min on first deploy)..."
if ! aws cloudformation deploy \
    --template-file .aws-sam/packaged.yaml \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "StackTag=${STACK_TAG}" \
    --no-fail-on-empty-changeset; then
    echo "  Deploy failed!"
    echo "  Check: aws cloudformation describe-stack-events --stack-name ${STACK_NAME} --region ${REGION}"
    exit 1
fi
echo "  OK"

# Step 5: Get outputs
echo "[5/6] Getting stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
    --output text)
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
    --output text)
PANEL_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='ControlPanelUrl'].OutputValue" \
    --output text)

# Step 6: Upload frontend
echo "[6/6] Uploading frontend..."
aws s3 sync frontend/ "s3://${BUCKET_NAME}/" --delete --region "${REGION}" > /dev/null
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths "/*" > /dev/null
echo "  OK"

# Cleanup bundled config
rm -f backend/accounts.json

echo ""
echo "========================================"
echo " DEPLOY COMPLETE!"
echo "========================================"
echo ""
echo " Panel URL: ${PANEL_URL}"
echo ""
echo " IMPORTANT: Edit config/accounts.json with your accounts,"
echo " instances and API keys before first use."
echo ""
echo " For multi-account, create the CloudControlRemoteAccess role"
echo " in each remote account (see docs/cross-account-setup.md)."
echo ""
