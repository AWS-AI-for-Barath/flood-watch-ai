# Routing Lambda + API Gateway Setup — FloodWatch Phase 4

Deploy the flood-aware routing API as a Lambda function behind API Gateway.

---

## Architecture

```
Client (GET /route?start=13.08,80.27&goal=12.95,80.22)
        ↓
API Gateway (HTTP API)
        ↓
Lambda (routingLambda)
  → PostGIS (flood_layer + flood_prediction)
  → OSRM (EC2 routing engine)
        ↓
JSON response (route + risk)
```

---

## Step 1: Create IAM Role

1. Go to **IAM** → **Roles** → **Create role**
2. Trusted entity: **AWS service** → **Lambda** → Next
3. Attach: `AWSLambdaVPCAccessExecutionRole` → Next
4. Role name: `FloodWatchRoutingRole` → Create

5. Open role → **Add permissions** → **Create inline policy** → JSON:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": ["rds-db:connect"],
            "Resource": "arn:aws:rds-db:us-east-1:*:dbuser:*/postgres"
        }
    ]
}
```

Policy name: `FloodWatchRoutingPolicy`

---

## Step 2: Create Lambda Function

1. **Lambda** → **Create function**
2. Name: `routingLambda`
3. Runtime: **Python 3.10**
4. Role: `FloodWatchRoutingRole`
5. Create

---

## Step 3: Configure Lambda

### General Configuration
- Memory: **512 MB**
- Timeout: **30 sec**

### VPC
- VPC: Default VPC
- Subnets: Same as RDS
- Security group: Same as RDS

### Environment Variables

| Key | Value |
|-----|-------|
| `DB_HOST` | `database-1.xxx.us-east-1.rds.amazonaws.com` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `floodwatch` |
| `DB_USER` | `postgres` |
| `DB_PASS` | *(your RDS password)* |
| `FLOODWATCH_DB_MODE` | `production` |
| `OSRM_ENDPOINT` | `http://<EC2_IP>:5000` |
| `OSRM_MOCK` | `1` *(set to `0` when EC2 is running)* |

### Layer
Add psycopg2 layer (same as Phase 3):
- ARN: Use your custom layer from Phase 3 setup

### Code
1. Package the `phase4_routing/` module as a ZIP
2. Upload to Lambda

```bash
cd floodwatch_ver1
pip install shapely -t package/
cp -r phase4_routing/ package/
cd package && zip -r ../routing_lambda.zip .
aws lambda update-function-code --function-name routingLambda --zip-file fileb://routing_lambda.zip
```

### Handler
Set handler to: `phase4_routing.routing.lambda_handler.handler`

---

## Step 4: Create API Gateway

1. **API Gateway** → **Create API** → **HTTP API** → Build
2. Integration: Lambda → `routingLambda`
3. API name: `FloodWatchRoutingAPI`
4. Create

5. Add route: `GET /route` → Integration: `routingLambda`
6. Deploy to `$default` stage

---

## Step 5: Test

```bash
curl "https://<API_ID>.execute-api.us-east-1.amazonaws.com/route?start=13.08,80.27&goal=12.95,80.22"
```

Expected response:
```json
{
  "status": "ok",
  "start": [13.08, 80.27],
  "goal": [12.95, 80.22],
  "route": [[13.08, 80.27], ..., [12.95, 80.22]],
  "risk_level": "low",
  "max_submergence_ratio": 0.0,
  "exposure_length": 0.0,
  "predicted_arrival_risk": 0.0
}
```

---

## Step 6: Run Phase 4 Schema in RDS

In **AWS CloudShell**, connect to your RDS and run:

```sql
-- Phase 4 tables (in addition to Phase 3 tables)
CREATE TABLE IF NOT EXISTS flood_prediction (
    id              SERIAL PRIMARY KEY,
    geometry        GEOMETRY(Polygon, 4326) NOT NULL,
    submergence_ratio FLOAT NOT NULL,
    velocity        FLOAT DEFAULT 0.0,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          VARCHAR(50) DEFAULT 'lisflood',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flood_pred_ts ON flood_prediction(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_flood_pred_geom ON flood_prediction USING GIST(geometry);

CREATE TABLE IF NOT EXISTS road_risk (
    id              SERIAL PRIMARY KEY,
    road_segment_id VARCHAR(100) NOT NULL UNIQUE,
    geometry        GEOMETRY(LineString, 4326),
    base_weight     FLOAT NOT NULL DEFAULT 1.0,
    dynamic_weight  FLOAT NOT NULL DEFAULT 1.0,
    max_submergence FLOAT DEFAULT 0.0,
    is_closed       BOOLEAN DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_road_risk_geom ON road_risk USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_road_risk_segment ON road_risk(road_segment_id);
```

---

## Cost Estimate

| Resource | Cost |
|----------|------|
| Lambda (per 1K requests) | ~$0.002 |
| API Gateway (per 1M requests) | ~$1.00 |
| **Monthly (light usage)** | **< $1** |
