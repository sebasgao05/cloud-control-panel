# ============================================================
# Cloud Control Panel - Setup de prueba cross-account
# ============================================================
# Este script crea un rol IAM en TU MISMA cuenta para simular
# el flujo multi-cuenta sin necesitar una segunda cuenta AWS.
#
# La Lambda hara AssumeRole contra este rol y accederá EC2
# con credenciales temporales, exactamente como lo haría
# con una cuenta remota real.
#
# Uso:
#   .\mock\setup-cross-account-test.ps1
#
# Limpiar despues de probar:
#   .\mock\setup-cross-account-test.ps1 -Cleanup
# ============================================================

param(
    [switch]$Cleanup
)

$ErrorActionPreference = "Stop"
$RoleName = "CloudControlRemoteAccess"
$PolicyName = "EC2Access"
$AccountId = (aws sts get-caller-identity --query "Account" --output text).Trim()
$LambdaRoleArn = "arn:aws:iam::${AccountId}:role/cloud-control-lambda-ccp-main"

if ($Cleanup) {
    Write-Host ""
    Write-Host "=== Limpiando recursos de prueba cross-account ===" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "  Eliminando policy del rol..."
    aws iam delete-role-policy --role-name $RoleName --policy-name $PolicyName 2>$null
    
    Write-Host "  Eliminando rol..."
    aws iam delete-role --role-name $RoleName 2>$null
    
    Write-Host ""
    Write-Host "  Limpieza completa." -ForegroundColor Green
    Write-Host "  Recuerda quitar la cuenta 'cross-test' de config/accounts.json" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "=== Setup de prueba cross-account ===" -ForegroundColor Cyan
Write-Host "  Cuenta: $AccountId"
Write-Host "  Lambda Role: $LambdaRoleArn"
Write-Host ""

# Paso 1: Crear trust policy
$TrustPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "$LambdaRoleArn"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@

$TrustPolicyFile = [System.IO.Path]::GetTempFileName()
$TrustPolicy | Out-File -FilePath $TrustPolicyFile -Encoding utf8

# Paso 2: Crear rol
Write-Host "[1/3] Creando rol $RoleName..." -ForegroundColor Yellow
$existingRole = aws iam get-role --role-name $RoleName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Rol ya existe, continuando..." -ForegroundColor Gray
} else {
    aws iam create-role `
        --role-name $RoleName `
        --assume-role-policy-document "file://$TrustPolicyFile" `
        --description "Cloud Control Panel - cross account test role" | Out-Null
    Write-Host "  OK" -ForegroundColor Green
}

Remove-Item $TrustPolicyFile -ErrorAction SilentlyContinue

# Paso 3: Crear EC2 policy
$Ec2Policy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StartInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*"
    }
  ]
}
"@

$Ec2PolicyFile = [System.IO.Path]::GetTempFileName()
$Ec2Policy | Out-File -FilePath $Ec2PolicyFile -Encoding utf8

Write-Host "[2/3] Adjuntando policy EC2..." -ForegroundColor Yellow
aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name $PolicyName `
    --policy-document "file://$Ec2PolicyFile" | Out-Null
Write-Host "  OK" -ForegroundColor Green

Remove-Item $Ec2PolicyFile -ErrorAction SilentlyContinue

# Paso 4: Mostrar instrucciones
Write-Host "[3/3] Rol listo." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " SETUP COMPLETO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host " Rol ARN: arn:aws:iam::${AccountId}:role/$RoleName" -ForegroundColor Yellow
Write-Host ""
Write-Host " Ahora agrega esto en config/accounts.json dentro de 'accounts':" -ForegroundColor Gray
Write-Host ""
Write-Host @"
    {
      "id": "cross-test",
      "name": "Cross-Account Test",
      "awsAccountId": "$AccountId",
      "region": "us-east-1",
      "crossAccountRoleArn": "arn:aws:iam::${AccountId}:role/$RoleName",
      "instances": [
        {
          "id": "test-via-role",
          "name": "Instancia (via AssumeRole)",
          "instanceId": "<TU_INSTANCE_ID>",
          "description": "Prueba cross-account con la misma instancia",
          "dashboardPort": null,
          "group": null
        }
      ],
      "groups": []
    }
"@ -ForegroundColor White
Write-Host ""
Write-Host " Luego ejecuta: .\deploy.ps1 -StackTag 'ccp-main'" -ForegroundColor Gray
Write-Host ""
Write-Host " Para limpiar despues: .\mock\setup-cross-account-test.ps1 -Cleanup" -ForegroundColor Gray
Write-Host ""
