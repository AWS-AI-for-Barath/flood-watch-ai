# Phase 5: processFloodAlerts Deployment Guide

This guide details exactly how to deploy the real AWS implementation of the FloodWatch Phase 5 mass alerting module.

## Architecture

```
Phase 4 (LISFLOOD Lambda)
        |
        v
EventBridge Rule (phase4_simulation_completed)
        |
        v
Lambda (processFloodAlerts)
        |-- Query PostGIS (registered_users)
        |-- Check DynamoDB (alert_history) for Rate Limit
        |-- Generate Multilingual Messages
        |-- Dispatch SMS via Amazon Pinpoint
        |-- Synthesize Voice via Amazon Polly
        v
Users (SMS / Voice)
```

---

## Prerequisites

1. Phase 3 & 4 deployed with active RDS instance.
2. An **Amazon Pinpoint** project created in the Console (to get an App ID).
3. A verified phone number or SMS Sandbox active in Pinpoint (if in sandbox mode, you can only text verified numbers).

---

## Step 1: Create DynamoDB Table

We need `alert_history` to track alerts and enforce the 15-minute rate limit.

1. Go to **DynamoDB** -> Tables -> **Create table**.
2. Table name: `alert_history`
3. Partition key: `user_id` (String)
4. Sort key: `timestamp` (String)
5. Leave other settings default and click **Create**.

---

## Step 2: Ensure PostGIS Schema Exists

Run this in your RDS instance to create the users table:

```bash
# Get DB password and run psql
psql -h <DB_HOST> -U postgres -d floodwatch -f infra/phase5/schema.sql
```

## Step 3: Create IAM Role

See `iam-policy.json`. Provide this policy to a new Lambda execution role. It grants access to:
- Pinpoint SMS (`mobiletargeting:SendMessages`)
- Polly Speech (`polly:SynthesizeSpeech`)
- DynamoDB (`dynamodb:*` on `alert_history`)
- RDS Connect (`rds-db:connect`)
- CloudWatch logs.

---

## Step 4: Deploy the Lambda Function

1. **Lambda Console** -> **Create function**
2. Name: `processFloodAlerts`
3. Runtime: **Python 3.12**
4. Role: The one created in Step 3.
5. Configuration -> **Memory**: 512 MB. **Timeout**: 60 sec.

### Environment Variables

| Key | Value | Notes |
|-----|-------|-------|
| `DB_HOST` | *(your-rds.endpoint.com)* | Required |
| `DB_PORT` | `5432` | Required |
| `DB_NAME` | `floodwatch` | Required |
| `DB_USER` | `postgres` | Required |
| `DB_PASS` | *(your-rds-password)* | Required |
| `FLOODWATCH_ALERT_MODE` | `production` | Enables Pinpoint/Polly |
| `PINPOINT_APP_ID` | *(your-pinpoint-id)* | Required for SMS |
| `ALERT_HISTORY_TABLE` | `alert_history` | Defaults to this |

### VPC Configuration
Because it must reach RDS PostGIS, attach the Lambda to the same **VPC, Subnets, and Security Group** as your RDS instance.

### Add layer for psycopg2
Use ARN: `arn:aws:lambda:us-east-1:898466741470:layer:psycopg2-py310:1`

### Package code and upload

```bash
cd flood-watch-ai
mkdir -p package
# Add dependencies
pip install shapely -t package/
# Copy code
cp -r alerting/ package/
cp -r phase4_routing/ package/
cp infra/lambda_floodwatchAlert/lambda_handler.py package/
cd package && zip -r ../alert_lambda.zip .
aws lambda update-function-code --function-name processFloodAlerts --zip-file fileb://alert_lambda.zip
```

**Handler:** `lambda_handler.handler`

---

## Step 5: EventBridge Setup

Follow `infra/phase5/eventbridge_setup.md` to map the custom Phase 4 event to this Lambda.

---

## Step 6: Deploy Dashboard API

Deploy `alerting/dashboard_api.py` as a separate Lambda attached to an **API Gateway HTTP API** with a `GET /alerts/recent` route. Assign it a role with `dynamodb:Scan` permissions to the `alert_history` table. No VPC needed (DynamoDB is public AWS API).

---

## Testing Verification

You can test by triggering the `processFloodAlerts` Lambda via the Test tab with a sample Phase 4 event containing polygons over registered users (see `eventbridge_setup.md`).

Look for:
1. "Pinpoint SMS sent to +91..."
2. "Stored alert alert_xxxx in DynamoDB"

## Cost Envelope

- Pinpoint SMS: ~$0.00645 per message sent to India.
- Polly Synthesize: ~$4.00 per 1M characters (extremely cheap).
- Lambda & DDB: Well within free tier / minimal cost.
- PostGIS: Included in existing Phase 3/4 RDS footprint.
