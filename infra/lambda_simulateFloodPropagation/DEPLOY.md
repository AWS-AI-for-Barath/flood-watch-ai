# Phase 4: simulateFloodPropagation Deployment Guide

## Architecture

```
Phase 3 stores flood polygon
        |
        v
S3 trigger (analysis/* prefix) -OR- EventBridge schedule
        |
        v
Lambda (simulateFloodPropagation)
        |-- Read flood_layer table (Phase 3 observed polygons)
        |-- Query DEM terrain elevation from dem_table
        |-- Compute terrain slope + flow direction
        |-- Expand flood zones downstream (depth decay)
        |-- Store predicted polygons in flood_prediction table
        v
flood_prediction table (used by routingLambda)
```

---

## Step 1: Create Lambda Function

1. **Lambda Console** -> **Create function**
2. Settings:
   - Function name: `simulateFloodPropagation`
   - Runtime: **Python 3.12**
   - Architecture: **x86_64**
   - Execution role: Use existing `FloodWatchLambdaRole` or create new with `iam-policy.json`
3. Click **Create function**

### Configure:

**General Configuration:**
- Memory: **512 MB**
- Timeout: **60 seconds**

**VPC Configuration:**
- VPC: Same as RDS (default VPC)
- Subnets: Same as RDS
- Security group: Same as RDS

**Environment Variables:**

| Key | Value |
|-----|-------|
| `DB_HOST` | `database-1.ckdm4y6i86ke.us-east-1.rds.amazonaws.com` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `floodwatch` |
| `DB_USER` | `postgres` |
| `DB_PASS` | *(your RDS password)* |
| `FLOODWATCH_DB_MODE` | `production` |

**Add Layer:**
- psycopg2 layer: `arn:aws:lambda:us-east-1:898466741470:layer:psycopg2-py310:1`

**Package and Upload:**
```bash
cd flood-watch-ai
mkdir -p package
cp -r phase4_routing/ package/
cp infra/lambda_simulateFloodPropagation/lambda_handler.py package/
cd package && zip -r ../propagation_lambda.zip .
aws lambda update-function-code --function-name simulateFloodPropagation --zip-file fileb://propagation_lambda.zip
```

**Handler:** `lambda_handler.handler`

---

## Step 2: Add S3 Trigger

1. In Lambda console, click **Add trigger**
2. Select **S3**
3. Bucket: `floodwatch-uploads`
4. Event type: `s3:ObjectCreated:*`
5. Prefix: `analysis/`
6. Suffix: `.json`
7. Click **Add**

This triggers propagation every time Phase 3 stores a new flood analysis.

---

## Step 3: Verify routingLambda Environment

Ensure the existing `routingLambda` has:

| Key | Value |
|-----|-------|
| `FLOODWATCH_DB_MODE` | `production` |
| `OSRM_MOCK` | `0` |

This ensures:
- Routing uses real PostGIS flood data
- OSRM queries the real public server
- Inline propagation runs during route requests (backup)

---

## Step 4: Create flood_prediction Schema

If not already created, run in RDS:

```sql
CREATE TABLE IF NOT EXISTS flood_prediction (
    id              SERIAL PRIMARY KEY,
    geometry        GEOMETRY(Polygon, 4326),
    submergence_ratio DOUBLE PRECISION DEFAULT 0.0,
    velocity        DOUBLE PRECISION DEFAULT 0.0,
    timestamp       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source          VARCHAR(50) DEFAULT 'lisflood'
);

CREATE INDEX IF NOT EXISTS idx_flood_prediction_ts
    ON flood_prediction (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_flood_prediction_geom
    ON flood_prediction USING GIST (geometry);
```

---

## Step 5: Test

### Manual Lambda test event:
```json
{
  "source": "manual",
  "detail-type": "test_propagation"
}
```

### Expected response:
```json
{
  "statusCode": 200,
  "body": "{\"status\":\"ok\",\"source_polygons\":3,\"predictions_stored\":3}"
}
```

### Verify predictions stored:
```sql
SELECT id, submergence_ratio, source, timestamp
FROM flood_prediction
ORDER BY timestamp DESC
LIMIT 10;
```

---

## Cost Estimate

| Resource | Cost |
|----------|------|
| Lambda (per run, 512MB, <60s) | ~$0.01 |
| PostGIS queries (existing RDS) | $0.00 (included) |
| **Total per propagation** | **< $0.01** |
