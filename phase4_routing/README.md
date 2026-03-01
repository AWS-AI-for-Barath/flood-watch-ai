# FloodWatch AI — Phase 4: Hydrodynamic Routing Pipeline

Production-ready AWS hydrodynamic simulation and flood-aware routing system.
Consumes Phase 3's mocked flood polygons and feeds risk-scored routes to Phase 5's alert system.

## Architecture

```
SageMaker Processing Job (LISFLOOD mock container)
        ↓
Flood depth + velocity raster (.npy → S3)
        ↓
Lambda: raster_to_geojson
        ↓
PostGIS flood_prediction table (time-indexed)
        ↓
Road Risk Updater (dynamic weight engine)
        ↓
OSRM EC2 routing engine (port 5000)
        ↓
Routing API (Lambda + API Gateway)
        ↓
Phase 5 Alert System
```

## Directory Structure

```
phase4_routing/
├── lisflood/           # LISFLOOD simulation pipeline
│   ├── mock_container.py       # Mock raster generator
│   ├── sagemaker_job.py        # SageMaker Processing Job launcher
│   └── raster_to_geojson.py    # Raster → GeoJSON Lambda
├── db/                 # PostGIS database layer
│   ├── schema.sql              # Table definitions
│   ├── connection.py           # Dual-mode connection (mock/production)
│   └── flood_store.py          # CRUD operations
├── routing/            # Routing engine
│   ├── risk_levels.py          # Weight tier constants
│   ├── road_risk_updater.py    # Dynamic weight engine
│   ├── routing_api.py          # Core routing logic
│   └── lambda_handler.py       # API Gateway Lambda wrapper
├── osrm/               # OSRM integration
│   ├── osrm_client.py          # HTTP client + mock
│   ├── ec2_setup.sh            # EC2 bootstrap script
│   └── flood_profile.lua       # Custom Lua routing profile
├── infra/              # AWS infrastructure configs
│   ├── sagemaker_config.json
│   ├── iam_roles.json
│   ├── eventbridge_schedule.json
│   ├── api_gateway.json
│   ├── cloudwatch.json
│   └── deploy_phase4.ps1
└── tests/              # All tests (mock-only, no AWS needed)
    ├── test_raster_to_geojson.py
    ├── test_road_risk_updater.py
    ├── test_routing_api.py
    ├── test_osrm_client.py
    └── test_local.py           # End-to-end local pipeline
```

## Quick Start

### Install Dependencies

```bash
pip install -r phase4_routing/requirements.txt
```

### Run Tests

```bash
# All Phase 4 tests
python -m pytest phase4_routing/tests/ -v

# End-to-end local test
python phase4_routing/tests/test_local.py
```

### API Usage

```
GET /route?start=13.08,80.27&goal=12.95,80.22
```

**Response:**
```json
{
  "status": "ok",
  "start": [13.08, 80.27],
  "goal": [12.95, 80.22],
  "route": [[13.08, 80.27], ...],
  "risk_level": "low",
  "max_submergence_ratio": 0.0,
  "exposure_length": 0.0,
  "predicted_arrival_risk": 0.0
}
```

### Road Risk Weight Tiers

| Submergence Ratio | Multiplier | Risk Level |
|---|---|---|
| < 0.2 | base × 1 | low |
| 0.2 – 0.4 | base × 2 | moderate |
| 0.4 – 0.7 | base × 5 | high |
| > 0.7 | ∞ (closed) | severe |

## Input Contract (Phase 3)

Flood polygons consumed from Phase 3:

```json
{
  "type": "FeatureCollection",
  "features": [{
    "geometry": "Polygon",
    "properties": {
      "submergence_ratio": 0.45,
      "timestamp": "2026-03-01T18:00:00Z"
    }
  }]
}
```

## AWS Deployment

```powershell
.\phase4_routing\infra\deploy_phase4.ps1
```

Deploys: IAM roles, Lambda functions, API Gateway (GET /route), EventBridge schedule (15 min).

## Branch

All Phase 4 code lives on: `feature/phase4-hydrodynamic-routing`
