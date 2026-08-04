# Cloud Control Panel - Deploy Script (Multi-account version)
# Usage: .\deploy.ps1 [-StackTag "ccp-main"]
# Prerequisites: AWS CLI configured with principal account

param(
    [string]$StackTag = "ccp-main",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"
$StackName = "cloud-control-$StackTag"
$AccountId = (aws sts get-caller-identity --query "Account" --output text).Trim()
$S3Bucket = "cloud-control-deploy-$AccountId"

Write-Host ""
Write-Host "=== Cloud Control Panel Deploy (Multi-account) ===" -ForegroundColor Cyan
Write-Host "  Stack: $StackName"
Write-Host "  Account: $AccountId"
Write-Host "  Region: $Region"
Write-Host ""

# Step 1: Create deployment bucket if needed
Write-Host "[1/6] Checking deploy bucket..." -ForegroundColor Yellow
$bucketExists = aws s3api head-bucket --bucket $S3Bucket 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Creating bucket: $S3Bucket"
    aws s3api create-bucket --bucket $S3Bucket --region $Region | Out-Null
}
Write-Host "  OK" -ForegroundColor Green

# Step 2: Copy accounts.json to backend (bundled with Lambda)
Write-Host "[2/6] Bundling config with Lambda..." -ForegroundColor Yellow
Copy-Item "config\accounts.json" "backend\accounts.json" -Force
Write-Host "  OK" -ForegroundColor Green

# Step 3: Package CloudFormation
Write-Host "[3/6] Packaging CloudFormation template..." -ForegroundColor Yellow
if (-not (Test-Path ".aws-sam")) { New-Item -ItemType Directory -Path ".aws-sam" | Out-Null }
aws cloudformation package `
    --template-file template.yaml `
    --s3-bucket $S3Bucket `
    --s3-prefix cfn `
    --output-template-file .aws-sam\packaged.yaml `
    --region $Region | Out-Null
Write-Host "  OK" -ForegroundColor Green

# Step 4: Deploy stack
Write-Host "[4/6] Deploying stack (3-5 min on first deploy)..." -ForegroundColor Yellow
aws cloudformation deploy `
    --template-file .aws-sam\packaged.yaml `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides "StackTag=$StackTag" `
    --no-fail-on-empty-changeset

if ($LASTEXITCODE -ne 0) {
    Write-Host "  Deploy failed!" -ForegroundColor Red
    Write-Host "  Check: aws cloudformation describe-stack-events --stack-name $StackName --region $Region"
    exit 1
}
Write-Host "  OK" -ForegroundColor Green

# Step 5: Get outputs
Write-Host "[5/6] Getting stack outputs..." -ForegroundColor Yellow
$outputs = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
$bucketName = ($outputs | Where-Object { $_.OutputKey -eq "FrontendBucketName" }).OutputValue
$distributionId = ($outputs | Where-Object { $_.OutputKey -eq "DistributionId" }).OutputValue
$panelUrl = ($outputs | Where-Object { $_.OutputKey -eq "ControlPanelUrl" }).OutputValue

# Step 6: Upload frontend
Write-Host "[6/6] Uploading frontend..." -ForegroundColor Yellow
aws s3 sync frontend/ "s3://$bucketName/" --delete --region $Region | Out-Null
aws cloudfront create-invalidation --distribution-id $distributionId --paths "/*" | Out-Null
Write-Host "  OK" -ForegroundColor Green

# Cleanup bundled config
Remove-Item "backend\accounts.json" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " DEPLOY COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host " Panel URL: $panelUrl" -ForegroundColor Yellow
Write-Host ""
Write-Host " IMPORTANTE: Edita config/accounts.json con tus cuentas," -ForegroundColor Gray
Write-Host " instancias y API keys antes del primer uso." -ForegroundColor Gray
Write-Host ""
Write-Host " Para multi-cuenta, crea el rol CloudControlRemoteAccess" -ForegroundColor Gray
Write-Host " en cada cuenta remota (ver docs/cross-account-setup.md)." -ForegroundColor Gray
Write-Host ""
