# ============================================================
# FloodWatch Phase 1 AWS Deployment Script
# Deploys: S3 bucket, Lambda, IAM role, API Gateway (HTTP API)
# ============================================================

$ErrorActionPreference = 'Stop'
$env:AWS_PAGER = ''
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')

$REGION = 'us-east-1'
$BUCKET_NAME = 'floodwatch-uploads'
$FUNCTION_NAME = 'floodwatch-presign'
$ROLE_NAME = 'floodwatch-lambda-role'
$POLICY_NAME = 'floodwatch-lambda-s3-policy'
$API_NAME = 'floodwatch-api'
$INFRA_DIR = $PSScriptRoot

Write-Host ''
Write-Host '=======================================' -ForegroundColor Cyan
Write-Host '  FloodWatch Phase 1 AWS Deployment' -ForegroundColor Cyan
Write-Host '=======================================' -ForegroundColor Cyan
Write-Host ''

# --- 1. Verify AWS CLI ---
Write-Host '[1/7] Verifying AWS CLI...' -ForegroundColor Yellow
try {
    $awsVersion = aws --version 2>&1
    Write-Host "  OK: $awsVersion" -ForegroundColor Green
}
catch {
    Write-Host '  ERROR: AWS CLI not found.' -ForegroundColor Red
    exit 1
}

$identityRaw = aws sts get-caller-identity --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host '  ERROR: AWS credentials not configured. Run: aws configure' -ForegroundColor Red
    exit 1
}
$accountId = ($identityRaw | ConvertFrom-Json).Account
Write-Host "  Account: $accountId" -ForegroundColor Green

# --- 2. Create S3 Bucket ---
Write-Host "[2/7] Creating S3 bucket: $BUCKET_NAME ..." -ForegroundColor Yellow
aws s3api head-bucket --bucket $BUCKET_NAME 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Bucket already exists, skipping.' -ForegroundColor DarkYellow
}
else {
    if ($REGION -eq 'us-east-1') {
        aws s3api create-bucket --bucket $BUCKET_NAME --region $REGION | Out-Null
    }
    else {
        aws s3api create-bucket --bucket $BUCKET_NAME --region $REGION --create-bucket-configuration LocationConstraint=$REGION | Out-Null
    }
    Write-Host '  Created.' -ForegroundColor Green
}

# Apply CORS
Write-Host '  Applying CORS...' -ForegroundColor Yellow
$corsFile = Join-Path $INFRA_DIR 'cors.json'
aws s3api put-bucket-cors --bucket $BUCKET_NAME --cors-configuration ('file://' + $corsFile)
Write-Host '  CORS applied.' -ForegroundColor Green

# Enable EventBridge notifications
Write-Host '  Enabling EventBridge notifications...' -ForegroundColor Yellow
$ebConfig = '{"EventBridgeConfiguration":{}}'
aws s3api put-bucket-notification-configuration --bucket $BUCKET_NAME --notification-configuration $ebConfig
Write-Host '  EventBridge enabled.' -ForegroundColor Green

# --- 3. Create IAM Role ---
Write-Host "[3/7] Creating IAM role: $ROLE_NAME ..." -ForegroundColor Yellow
$trustFile = Join-Path $INFRA_DIR 'trust-policy.json'
aws iam get-role --role-name $ROLE_NAME 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Role already exists, skipping creation.' -ForegroundColor DarkYellow
    $roleJson = aws iam get-role --role-name $ROLE_NAME --output json
    $ROLE_ARN = ($roleJson | ConvertFrom-Json).Role.Arn
}
else {
    $roleResult = aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document ('file://' + $trustFile) --output json
    $ROLE_ARN = ($roleResult | ConvertFrom-Json).Role.Arn
    Write-Host "  Created: $ROLE_ARN" -ForegroundColor Green
    Write-Host '  Waiting 10s for IAM propagation...' -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}

# --- 4. Attach Policy ---
Write-Host '[4/7] Attaching S3 policy to role...' -ForegroundColor Yellow
$policyArn = "arn:aws:iam::${accountId}:policy/${POLICY_NAME}"
$policyFile = Join-Path $INFRA_DIR 'lambda-s3-policy.json'

aws iam get-policy --policy-arn $policyArn 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Policy exists, skipping.' -ForegroundColor DarkYellow
}
else {
    $policyResult = aws iam create-policy --policy-name $POLICY_NAME --policy-document ('file://' + $policyFile) --output json
    $policyArn = ($policyResult | ConvertFrom-Json).Policy.Arn
    Write-Host '  Policy created.' -ForegroundColor Green
}
aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn $policyArn
Write-Host '  Policy attached.' -ForegroundColor Green

# --- 5. Package Lambda ---
Write-Host '[5/7] Packaging Lambda function...' -ForegroundColor Yellow
$zipPath = Join-Path $INFRA_DIR 'lambda_presign.zip'
$lambdaSrc = Join-Path $INFRA_DIR 'lambda_presign' 'lambda_function.py'
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $lambdaSrc -DestinationPath $zipPath
Write-Host '  Packaged: lambda_presign.zip' -ForegroundColor Green

# --- 6. Deploy Lambda ---
Write-Host "[6/7] Deploying Lambda: $FUNCTION_NAME ..." -ForegroundColor Yellow
$envVars = 'Variables={BUCKET_NAME=' + $BUCKET_NAME + ',ALLOWED_ORIGINS=*}'

aws lambda get-function --function-name $FUNCTION_NAME 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Function exists, updating code...' -ForegroundColor DarkYellow
    aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file ('fileb://' + $zipPath) --output json | Out-Null
    Start-Sleep -Seconds 3
    aws lambda update-function-configuration --function-name $FUNCTION_NAME --environment $envVars --output json | Out-Null
}
else {
    aws lambda create-function --function-name $FUNCTION_NAME --runtime python3.12 --handler lambda_function.handler --role $ROLE_ARN --zip-file ('fileb://' + $zipPath) --timeout 10 --memory-size 128 --environment $envVars --region $REGION --output json | Out-Null
}
Write-Host '  Lambda deployed.' -ForegroundColor Green

# --- 7. Create HTTP API Gateway ---
Write-Host "[7/7] Creating HTTP API Gateway: $API_NAME ..." -ForegroundColor Yellow

$apisRaw = aws apigatewayv2 get-apis --output json
$apis = $apisRaw | ConvertFrom-Json
$existingApi = $apis.Items | Where-Object { $_.Name -eq $API_NAME }

if ($existingApi) {
    $API_ID = $existingApi.ApiId
    Write-Host "  API already exists: $API_ID" -ForegroundColor DarkYellow
}
else {
    $corsJson = '{"AllowOrigins":["*"],"AllowMethods":["POST","OPTIONS"],"AllowHeaders":["Content-Type"],"MaxAge":3600}'
    $apiResult = aws apigatewayv2 create-api --name $API_NAME --protocol-type HTTP --cors-configuration $corsJson --output json
    $API_ID = ($apiResult | ConvertFrom-Json).ApiId
    Write-Host "  Created API: $API_ID" -ForegroundColor Green
}

# Create Lambda integration
$lambdaFnJson = aws lambda get-function --function-name $FUNCTION_NAME --output json
$LAMBDA_ARN = ($lambdaFnJson | ConvertFrom-Json).Configuration.FunctionArn

$integrationResult = aws apigatewayv2 create-integration --api-id $API_ID --integration-type AWS_PROXY --integration-uri $LAMBDA_ARN --payload-format-version '2.0' --output json
$INTEGRATION_ID = ($integrationResult | ConvertFrom-Json).IntegrationId

# Create route: POST /api/presign
aws apigatewayv2 create-route --api-id $API_ID --route-key 'POST /api/presign' --target "integrations/$INTEGRATION_ID" --output json 2>$null | Out-Null

# Create default stage with auto-deploy
aws apigatewayv2 get-stage --api-id $API_ID --stage-name '$default' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    aws apigatewayv2 create-stage --api-id $API_ID --stage-name '$default' --auto-deploy --output json | Out-Null
}

# Grant API Gateway permission to invoke Lambda
$SOURCE_ARN = "arn:aws:execute-api:${REGION}:${accountId}:${API_ID}/*/*/api/presign"
$stmtId = 'apigateway-invoke-' + (Get-Random)
aws lambda add-permission --function-name $FUNCTION_NAME --statement-id $stmtId --action 'lambda:InvokeFunction' --principal apigateway.amazonaws.com --source-arn $SOURCE_ARN 2>$null | Out-Null

$API_ENDPOINT = "https://${API_ID}.execute-api.${REGION}.amazonaws.com"

# --- Done ---
Write-Host ''
Write-Host '=======================================' -ForegroundColor Green
Write-Host '  DEPLOYMENT COMPLETE' -ForegroundColor Green
Write-Host '=======================================' -ForegroundColor Green
Write-Host ''
Write-Host "  S3 Bucket:    $BUCKET_NAME" -ForegroundColor White
Write-Host "  Lambda:       $FUNCTION_NAME" -ForegroundColor White
Write-Host "  API Endpoint: $API_ENDPOINT" -ForegroundColor Cyan
Write-Host ''
Write-Host '  Update frontend/upload.js:' -ForegroundColor Yellow
Write-Host "    const API_BASE_URL = '$API_ENDPOINT';" -ForegroundColor White
Write-Host ''
Write-Host '  Test the endpoint:' -ForegroundColor Yellow
Write-Host "    POST $API_ENDPOINT/api/presign" -ForegroundColor White
Write-Host ''
