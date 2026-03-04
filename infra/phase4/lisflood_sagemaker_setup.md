# LISFLOOD-FP SageMaker Setup — FloodWatch Phase 4

Deploy the LISFLOOD-FP hydrodynamic simulation as a SageMaker Processing Job.

---

## Architecture

```
S3 (DEM + rainfall data)
        ↓
SageMaker Processing Job
  (LISFLOOD-FP container)
        ↓
S3 (flood depth + velocity rasters)
        ↓
Lambda (raster_to_geojson)
        ↓
PostGIS (flood_prediction table)
```

---

## Step 1: Prepare DEM Data

Upload Chennai-region DEM raster to S3:

```bash
aws s3 cp chennai_dem.tif s3://floodwatch-uploads/lisflood/input/dem/
```

---

## Step 2: Prepare Rainfall Data

Upload rainfall scenario files:

```bash
aws s3 cp rainfall_scenario.csv s3://floodwatch-uploads/lisflood/input/rainfall/
```

---

## Step 3: Build LISFLOOD Container

```bash
# Clone mock container (upgradeable to real LISFLOOD-FP later)
cd phase4_routing/lisflood/

# Build Docker image
docker build -t floodwatch-lisflood:latest .

# Tag and push to ECR
aws ecr create-repository --repository-name floodwatch-lisflood
aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker tag floodwatch-lisflood:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/floodwatch-lisflood:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/floodwatch-lisflood:latest
```

---

## Step 4: Run SageMaker Processing Job

```python
import sagemaker
from sagemaker.processing import ScriptProcessor

processor = ScriptProcessor(
    image_uri="<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/floodwatch-lisflood:latest",
    role="arn:aws:iam::<ACCOUNT_ID>:role/FloodWatchSageMakerRole",
    instance_count=1,
    instance_type="ml.m5.large",
    command=["python3"],
)

processor.run(
    code="phase4_routing/lisflood/mock_container.py",
    inputs=[
        sagemaker.processing.ProcessingInput(
            source="s3://floodwatch-uploads/lisflood/input/",
            destination="/opt/ml/processing/input",
        )
    ],
    outputs=[
        sagemaker.processing.ProcessingOutput(
            source="/opt/ml/processing/output",
            destination="s3://floodwatch-uploads/lisflood/output/",
        )
    ],
)
```

---

## Step 5: Convert Output Rasters

The `raster_to_geojson.py` Lambda auto-triggers when rasters land in S3:

1. Reads `flood_depth.npy` + `flood_velocity.npy` from S3
2. Extracts polygons using connected-component labelling
3. Stores as GeoJSON in `flood_prediction` table via `flood_store.store_predictions()`

---

## Step 6: IAM Role

Create `FloodWatchSageMakerRole` with these policies:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject"],
            "Resource": "arn:aws:s3:::floodwatch-uploads/lisflood/*"
        },
        {
            "Effect": "Allow",
            "Action": ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"],
            "Resource": "*"
        }
    ]
}
```

---

## Cost Estimate

| Resource | Cost |
|----------|------|
| ml.m5.large Processing Job (10 min) | ~$0.02/run |
| S3 storage (rasters) | < $0.01 |
| **Per simulation** | **~$0.03** |

> **Tip**: No persistent endpoints — only pay for processing time.

---

## Mock vs Production

| Component | Current (Mock) | Production |
|-----------|---------------|------------|
| Container | `mock_container.py` (synthetic rasters) | Real LISFLOOD-FP binary |
| Input | Random seed | Real DEM + rainfall |
| Output | Synthetic depth/velocity | Calibrated flood extent |

To upgrade: replace only `mock_container.py` with the real LISFLOOD-FP entrypoint. All downstream code (raster conversion, PostGIS storage, routing) works unchanged.
