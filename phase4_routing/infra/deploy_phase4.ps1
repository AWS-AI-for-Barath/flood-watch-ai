# ============================================================
# FloodWatch Phase 4 — AWS Deployment Script
# Deploys: IAM roles, Lambda functions, API Gateway, EventBridge
# ============================================================

$ErrorActionPreference = 'Stop'
$env:AWS_PAGER = ''
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')

$REGION = 'us-east-1'
$BUCKET_NAME = 'floodwatch-uploads'
$INFRA_DIR = $PSScriptRoot
$PHASE4_ROOT = Split-Path $INFRA_DIR

Write-Host ''
Write-Host '=======================================' -ForegroundColor Cyan
Write-Host '  FloodWatch Phase 4 AWS Deployment' -ForegroundColor Cyan
Write-Host '=======================================' -ForegroundColor Cyan
Write-Host ''

# --- 1. Verify AWS CLI ---
Write-Host '[1/8] Verifying AWS CLI...' -ForegroundColor Yellow
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

# --- 2. Create IAM Roles ---
Write-Host '[2/8] Creating IAM roles...' -ForegroundColor Yellow

$roles = @(
    @{ Name = 'floodwatch-sagemaker-role';     Service = 'sagemaker.amazonaws.com' },
    @{ Name = 'floodwatch-raster-lambda-role'; Service = 'lambda.amazonaws.com' },
    @{ Name = 'floodwatch-routing-api-role';   Service = 'lambda.amazonaws.com' }
)

foreach ($role in $roles) {
    aws iam get-role --role-name $role.Name 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Role $($role.Name) already exists, skipping." -ForegroundColor DarkYellow
    }
    else {
        $trustPolicy = @{
            Version = '2012-10-17'
            Statement = @(@{
                Effect = 'Allow'
                Principal = @{ Service = $role.Service }
                Action = 'sts:AssumeRole'
            })
        } | ConvertTo-Json -Depth 5 -Compress

        aws iam create-role --role-name $role.Name --assume-role-policy-document $trustPolicy --output json | Out-Null
        Write-Host "  Created: $($role.Name)" -ForegroundColor Green
    }
}
Write-Host '  Waiting 10s for IAM propagation...' -ForegroundColor Yellow
Start-Sleep -Seconds 10

# --- 3. Create S3 prefixes ---
Write-Host '[3/8] Creating S3 prefixes for LISFLOOD...' -ForegroundColor Yellow
aws s3api put-object --bucket $BUCKET_NAME --key 'lisflood/input/dem/' --content-length 0 2>$null | Out-Null
aws s3api put-object --bucket $BUCKET_NAME --key 'lisflood/input/rainfall/' --content-length 0 2>$null | Out-Null
aws s3api put-object --bucket $BUCKET_NAME --key 'lisflood/output/' --content-length 0 2>$null | Out-Null
Write-Host '  S3 prefixes created.' -ForegroundColor Green

# --- 4. Package Raster Lambda ---
Write-Host '[4/8] Packaging raster-to-geojson Lambda...' -ForegroundColor Yellow
$rasterZip = Join-Path $INFRA_DIR 'raster_lambda.zip'
if (Test-Path $rasterZip) { Remove-Item $rasterZip -Force }

$rasterSrc = Join-Path $PHASE4_ROOT 'lisflood' 'raster_to_geojson.py'
$dbDir = Join-Path $PHASE4_ROOT 'db'
Compress-Archive -Path $rasterSrc, $dbDir -DestinationPath $rasterZip
Write-Host '  Packaged: raster_lambda.zip' -ForegroundColor Green

# --- 5. Deploy Raster Lambda ---
Write-Host '[5/8] Deploying raster-to-geojson Lambda...' -ForegroundColor Yellow
$RASTER_FN = 'floodwatch-raster-to-geojson'
$rasterRoleArn = "arn:aws:iam::${accountId}:role/floodwatch-raster-lambda-role"

aws lambda get-function --function-name $RASTER_FN 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Function exists, updating...' -ForegroundColor DarkYellow
    aws lambda update-function-code --function-name $RASTER_FN --zip-file ('fileb://' + $rasterZip) --output json | Out-Null
}
else {
    aws lambda create-function --function-name $RASTER_FN --runtime python3.12 --handler raster_to_geojson.lambda_handler --role $rasterRoleArn --zip-file ('fileb://' + $rasterZip) --timeout 60 --memory-size 512 --region $REGION --output json | Out-Null
}
Write-Host '  Raster Lambda deployed.' -ForegroundColor Green

# --- 6. Package & Deploy Routing Lambda ---
Write-Host '[6/8] Deploying routing API Lambda...' -ForegroundColor Yellow
$routingZip = Join-Path $INFRA_DIR 'routing_lambda.zip'
if (Test-Path $routingZip) { Remove-Item $routingZip -Force }

$routingSrc = Join-Path $PHASE4_ROOT 'routing'
$osrmSrc = Join-Path $PHASE4_ROOT 'osrm'
Compress-Archive -Path $routingSrc, $osrmSrc, $dbDir -DestinationPath $routingZip

$ROUTING_FN = 'floodwatch-routing-handler'
$routingRoleArn = "arn:aws:iam::${accountId}:role/floodwatch-routing-api-role"

aws lambda get-function --function-name $ROUTING_FN 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  Function exists, updating...' -ForegroundColor DarkYellow
    aws lambda update-function-code --function-name $ROUTING_FN --zip-file ('fileb://' + $routingZip) --output json | Out-Null
}
else {
    $envVars = 'Variables={FLOODWATCH_DB_MODE=mock,OSRM_MOCK=1}'
    aws lambda create-function --function-name $ROUTING_FN --runtime python3.12 --handler phase4_routing.routing.lambda_handler.handler --role $routingRoleArn --zip-file ('fileb://' + $routingZip) --timeout 30 --memory-size 256 --environment $envVars --region $REGION --output json | Out-Null
}
Write-Host '  Routing Lambda deployed.' -ForegroundColor Green

# --- 7. Create API Gateway ---
Write-Host '[7/8] Creating API Gateway for routing...' -ForegroundColor Yellow
$API_NAME = 'floodwatch-routing-api'

$apisRaw = aws apigatewayv2 get-apis --output json
$apis = $apisRaw | ConvertFrom-Json
$existingApi = $apis.Items | Where-Object { $_.Name -eq $API_NAME }

if ($existingApi) {
    $API_ID = $existingApi.ApiId
    Write-Host "  API already exists: $API_ID" -ForegroundColor DarkYellow
}
else {
    $corsJson = '{"AllowOrigins":["*"],"AllowMethods":["GET","OPTIONS"],"AllowHeaders":["Content-Type"],"MaxAge":3600}'
    $apiResult = aws apigatewayv2 create-api --name $API_NAME --protocol-type HTTP --cors-configuration $corsJson --output json
    $API_ID = ($apiResult | ConvertFrom-Json).ApiId
    Write-Host "  Created API: $API_ID" -ForegroundColor Green
}

$lambdaFnJson = aws lambda get-function --function-name $ROUTING_FN --output json
$LAMBDA_ARN = ($lambdaFnJson | ConvertFrom-Json).Configuration.FunctionArn

$integrationResult = aws apigatewayv2 create-integration --api-id $API_ID --integration-type AWS_PROXY --integration-uri $LAMBDA_ARN --payload-format-version '2.0' --output json
$INTEGRATION_ID = ($integrationResult | ConvertFrom-Json).IntegrationId

aws apigatewayv2 create-route --api-id $API_ID --route-key 'GET /route' --target "integrations/$INTEGRATION_ID" --output json 2>$null | Out-Null

aws apigatewayv2 get-stage --api-id $API_ID --stage-name '$default' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    aws apigatewayv2 create-stage --api-id $API_ID --stage-name '$default' --auto-deploy --output json | Out-Null
}

$SOURCE_ARN = "arn:aws:execute-api:${REGION}:${accountId}:${API_ID}/*/*/route"
$stmtId = 'apigateway-invoke-' + (Get-Random)
aws lambda add-permission --function-name $ROUTING_FN --statement-id $stmtId --action 'lambda:InvokeFunction' --principal apigateway.amazonaws.com --source-arn $SOURCE_ARN 2>$null | Out-Null

$API_ENDPOINT = "https://${API_ID}.execute-api.${REGION}.amazonaws.com"

# --- 8. Create EventBridge Schedule ---
Write-Host '[8/8] Creating EventBridge schedule...' -ForegroundColor Yellow
$RULE_NAME = 'floodwatch-lisflood-schedule'

aws events put-rule --name $RULE_NAME --schedule-expression 'rate(15 minutes)' --state ENABLED --description 'Trigger LISFLOOD every 15 min' --output json 2>$null | Out-Null
Write-Host "  EventBridge rule created: $RULE_NAME" -ForegroundColor Green

# --- Done ---
Write-Host ''
Write-Host '=======================================' -ForegroundColor Green
Write-Host '  PHASE 4 DEPLOYMENT COMPLETE' -ForegroundColor Green
Write-Host '=======================================' -ForegroundColor Green
Write-Host ''
Write-Host "  Routing API:  $API_ENDPOINT/route" -ForegroundColor Cyan
Write-Host "  Test:         GET $API_ENDPOINT/route?start=13.08,80.27&goal=12.95,80.22" -ForegroundColor White
Write-Host "  EventBridge:  $RULE_NAME (every 15 min)" -ForegroundColor White
Write-Host ''
