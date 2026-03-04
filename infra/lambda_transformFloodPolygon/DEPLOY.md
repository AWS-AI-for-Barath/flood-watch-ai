# Phase 3: transformFloodPolygon Deployment Guide

## Architecture

```
S3 (analysis/*) → S3 Event → Lambda (transformFloodPolygon)
                                  ├── Read analysis/<uuid>.json
                                  ├── Read metadata/<uuid>.json
                                  ├── Query PostGIS DEM elevation
                                  ├── Compute water surface level
                                  ├── Generate flood polygon (ST_Buffer)
                                  ├── Store in flood_layer table
                                  └── Return GeoJSON FeatureCollection
```

---

## Step 1: Create RDS PostgreSQL Instance

1. Go to **RDS Console** → **Create database**
2. Choose:
   - **Engine**: PostgreSQL 15
   - **Template**: Free tier
   - **DB instance identifier**: `floodwatch-db`
   - **Master username**: `postgres`
   - **Master password**: *(choose and remember)*
   - **Instance class**: `db.t3.micro`
   - **Storage**: 20 GB gp3
   - **Public access**: **No** *(Lambda connects via VPC)*
3. **VPC**: Use your default VPC
4. **VPC security group**: Create new → `floodwatch-db-sg`
5. **Database name**: `floodwatch`
6. Click **Create database** (takes ~5 minutes)

### Configure Security Group
1. Go to **EC2 Console** → **Security Groups** → find `floodwatch-db-sg`
2. Edit **Inbound rules** → Add:
   - Type: **PostgreSQL** (port 5432)
   - Source: **Custom** → select your **default VPC CIDR** (e.g. `172.31.0.0/16`)
3. Save

### Note the Endpoint
1. Go back to RDS → click `floodwatch-db`
2. Copy the **Endpoint** (e.g. `floodwatch-db.abc123.us-east-1.rds.amazonaws.com`)

---

## Step 2: Initialize PostGIS Schema

### Option A: Using psql (if you have it)
```bash
psql -h floodwatch-db.abc123.us-east-1.rds.amazonaws.com -U postgres -d floodwatch -f sql/schema.sql
```

### Option B: Using AWS CloudShell
1. Open **AWS CloudShell** (top navigation bar)
2. Install psql: `sudo yum install -y postgresql15`
3. Connect:
```bash
psql -h floodwatch-db.abc123.us-east-1.rds.amazonaws.com -U postgres -d floodwatch
```
4. Paste the contents of `sql/schema.sql` and run
5. Verify:
```sql
SELECT 'flood_layer' AS tbl, COUNT(*) FROM flood_layer
UNION ALL
SELECT 'dem_table', COUNT(*) FROM dem_table;
```
Expected: `flood_layer: 0 rows`, `dem_table: 10 rows`

> **Note**: CloudShell runs in your VPC, so it can reach the RDS instance. If you get a connection timeout, ensure security group allows traffic from the VPC CIDR.

---

## Step 3: Create IAM Role

1. **IAM Console** → **Roles** → **Create role**
2. Trusted entity: **AWS service** → **Lambda** → Next
3. Attach managed policy: **AWSLambdaVPCAccessExecutionRole** *(needed for VPC)*
4. Next → Name: `FloodWatchTransformRole` → **Create role**
5. Open role → **Add permissions** → **Create inline policy** → JSON:
6. Paste contents of `iam-policy.json`
7. Name: `FloodWatchTransformPolicy` → Save

---

## Step 4: Add psycopg2 Lambda Layer

Lambda needs `psycopg2` to connect to PostgreSQL. Use a public pre-built layer:

**For us-east-1:**
```
arn:aws:lambda:us-east-1:898466741470:layer:psycopg2-py310:1
```

Alternative (if above doesn't work):
1. Download `psycopg2-binary` wheel for Linux
2. Package into a zip at `python/psycopg2/`
3. Upload as a custom Lambda Layer

---

## Step 5: Create Lambda Function

1. **Lambda Console** → **Create function**
2. Settings:
   - Function name: `transformFloodPolygon`
   - Runtime: **Python 3.10**
   - Architecture: **x86_64**
   - Execution role: **FloodWatchTransformRole**
3. Click **Create function**

### Configure:

**5a. General Configuration:**
- Memory: **512 MB**
- Timeout: **30 seconds**

**5b. VPC Configuration:**
1. **Configuration** → **VPC** → **Edit**
2. Select your **default VPC**
3. Select **at least 2 subnets** (same AZ as your RDS)
4. Security group: select `floodwatch-db-sg` (or default)
5. Save

**5c. Environment Variables:**

| Key | Value |
|-----|-------|
| `BUCKET_NAME` | `floodwatch-uploads` |
| `DB_HOST` | `floodwatch-db.abc123.us-east-1.rds.amazonaws.com` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `floodwatch` |
| `DB_USER` | `postgres` |
| `DB_PASS` | *(your RDS password)* |

**5d. Add Layer:**
- **Specify an ARN** → `arn:aws:lambda:us-east-1:898466741470:layer:psycopg2-py310:1`
- Click **Add**

**5e. Paste Code:**
1. Replace `lambda_function.py` with contents of `lambda_handler.py`
2. Click **Deploy**

---

## Step 6: Add S3 Trigger

1. Click **+ Add trigger**
2. Source: **S3**
3. Bucket: `floodwatch-uploads`
4. Event type: **PUT** (s3:ObjectCreated:Put)
5. Prefix: `analysis/`
6. Suffix: `.json`
7. Acknowledge → **Add**

---

## Step 7: Test

### Test via Lambda Console:
```json
{
  "Records": [{
    "s3": {
      "bucket": { "name": "floodwatch-uploads" },
      "object": { "key": "analysis/verify-phase2.json" }
    }
  }]
}
```

### Expected Output:
```json
{
  "statusCode": 200,
  "body": "{\"type\":\"FeatureCollection\",\"features\":[{\"type\":\"Feature\",\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[...]},\"properties\":{\"zone_id\":\"zone_verify-phase2\",\"submergence_ratio\":0.8,\"severity\":\"high\",\"timestamp\":\"...\"}}]}"
}
```

### Verify in RDS:
```sql
SELECT id, submergence_ratio, severity, water_surface_elevation,
       ST_AsText(ST_Centroid(geom)) AS center
FROM flood_layer;
```

---

## Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| RDS db.t3.micro (free tier, 12 months) | $0.00 |
| Lambda (100 invocations × 512MB × 30s) | ~$0.03 |
| **Total** | **~$0.03** |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Lambda timeout | Ensure Lambda is in same VPC/subnets as RDS |
| `psycopg2` import error | Verify Layer ARN is attached |
| Connection refused | Check security group allows port 5432 from VPC CIDR |
| `relation "flood_layer" does not exist` | Run `schema.sql` in RDS first |
| No metadata found | Lambda falls back to Chennai defaults (13.08, 80.27) |
