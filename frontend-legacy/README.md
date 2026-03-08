# FloodWatch PWA — Phase 1: Edge Ingestion & Community Input

Offline-first Progressive Web App that captures flood media (photo/video) with device telemetry and uploads to AWS S3 for downstream AI processing.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   MOBILE DEVICE                      │
│  ┌──────────────────────────────────────────────┐    │
│  │           FloodWatch PWA                     │    │
│  │                                              │    │
│  │  Camera ──► MediaRecorder (10s max)          │    │
│  │  GPS    ──► navigator.geolocation            │    │
│  │  IMU    ──► DeviceOrientationEvent           │    │
│  │                    │                         │    │
│  │              ┌─────▼──────┐                  │    │
│  │              │  IndexedDB │  (offline queue)  │    │
│  │              └─────┬──────┘                  │    │
│  │                    │                         │    │
│  │         ┌──────────▼──────────┐              │    │
│  │         │   Upload Manager    │              │    │
│  │         │  • Pre-signed URLs  │              │    │
│  │         │  • Retry (exp. bo.) │              │    │
│  │         │  • Background Sync  │              │    │
│  │         └──────────┬──────────┘              │    │
│  └────────────────────┼─────────────────────────┘    │
└───────────────────────┼──────────────────────────────┘
                        │ HTTPS PUT
                        ▼
┌───────────────────────────────────────────────────────┐
│                      AWS                              │
│                                                       │
│  ┌─────────────────────┐    ┌─────────────────────┐  │
│  │   S3: floodwatch-   │    │   API Gateway +     │  │
│  │       uploads        │    │   Lambda (presign)  │  │
│  │                      │    └─────────────────────┘  │
│  │  media/<uuid>.mp4    │                             │
│  │  metadata/<uuid>.json│                             │
│  └──────────┬───────────┘                             │
│             │ S3 ObjectCreated                        │
│             ▼                                         │
│  ┌──────────────────────┐                             │
│  │    EventBridge       │                             │
│  └──────────┬───────────┘                             │
│             │                                         │
│             ▼                                         │
│  ┌──────────────────────┐                             │
│  │   Step Functions     │──► Phase 2-5 AI Pipeline   │
│  └──────────────────────┘                             │
└───────────────────────────────────────────────────────┘
```

## Quick Start (Local Development)

```bash
# Serve the frontend (any static server works)
npx -y http-server ./frontend -p 8080

# Open in Chrome
# http://localhost:8080
```

> **Note:** Camera, GPS, and DeviceOrientation require HTTPS in production. `localhost` is exempt for development. For mobile device testing, use a tool like [ngrok](https://ngrok.com) to create an HTTPS tunnel.

## File Structure

```
frontend/
├── index.html          # PWA shell — viewfinder, controls, queue
├── manifest.json       # Installable PWA metadata
├── service-worker.js   # Offline caching + background sync
├── style.css           # Dark aquatic theme, mobile-first
├── app.js              # Camera, telemetry, capture orchestration
├── upload.js           # S3 upload queue, retry, IndexedDB
└── README.md           # This file
```

## S3 Bucket Setup

### Create the Bucket

```bash
aws s3 mb s3://floodwatch-uploads --region us-east-1
```

### CORS Configuration

Apply this CORS policy to `floodwatch-uploads` so the PWA can PUT directly via pre-signed URLs:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": [
      "https://your-domain.com",
      "http://localhost:8080"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

```bash
aws s3api put-bucket-cors \
  --bucket floodwatch-uploads \
  --cors-configuration file://cors.json
```

### Bucket Structure

```
floodwatch-uploads/
├── media/
│   ├── <uuid>.mp4      # Video captures
│   └── <uuid>.jpg      # Photo captures
└── metadata/
    └── <uuid>.json     # Telemetry + context
```

### Metadata Schema

```json
{
  "timestamp": "2026-02-28T12:45:00.000Z",
  "lat": 13.0827,
  "lon": 80.2707,
  "heading": 127.3,
  "pitch": -12.5,
  "yaw": 3.8,
  "device": "mobile",
  "filename": "a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg",
  "media_type": "image"
}
```

> **Contract:** These keys are consumed by the `main` branch AI pipeline (`src/pipeline.py`). Do not rename them.

## Pre-Signed URL Lambda

The PWA requests pre-signed PUT URLs from a backend endpoint. Here is a reference Lambda implementation:

```python
# lambda_presign.py
import json
import os
import boto3

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME', 'floodwatch-uploads')

def handler(event, context):
    body = json.loads(event['body'])
    media_key = body['mediaKey']         # e.g. "media/uuid.jpg"
    metadata_key = body['metadataKey']   # e.g. "metadata/uuid.json"

    media_url = s3.generate_presigned_url('put_object', Params={
        'Bucket': BUCKET,
        'Key': media_key,
        'ContentType': 'image/jpeg'  # or 'video/mp4'
    }, ExpiresIn=300)

    metadata_url = s3.generate_presigned_url('put_object', Params={
        'Bucket': BUCKET,
        'Key': metadata_key,
        'ContentType': 'application/json'
    }, ExpiresIn=300)

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'url': media_url,
            'metadataUrl': metadata_url
        })
    }
```

Deploy behind API Gateway and update `API_BASE_URL` in `upload.js`.

## EventBridge Trigger Setup

Create a rule that fires on S3 object creation in the `media/` prefix:

### 1. Enable S3 EventBridge Notifications

```bash
aws s3api put-bucket-notification-configuration \
  --bucket floodwatch-uploads \
  --notification-configuration '{
    "EventBridgeConfiguration": {}
  }'
```

### 2. Create EventBridge Rule

```bash
aws events put-rule \
  --name floodwatch-media-uploaded \
  --event-pattern '{
    "source": ["aws.s3"],
    "detail-type": ["Object Created"],
    "detail": {
      "bucket": { "name": ["floodwatch-uploads"] },
      "object": { "key": [{ "prefix": "media/" }] }
    }
  }'
```

### 3. Add Step Functions Target

```bash
aws events put-targets \
  --rule floodwatch-media-uploaded \
  --targets '[{
    "Id": "FloodWatchPipeline",
    "Arn": "arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:FloodWatchPipeline",
    "RoleArn": "arn:aws:iam::ACCOUNT_ID:role/EventBridgeStepFunctionsRole"
  }]'
```

## Step Functions Integration

The Step Functions state machine receives the S3 event and orchestrates:

```
S3 ObjectCreated (media/<uuid>.mp4)
    │
    ▼
Step Functions Start Execution
    │
    ├── 1. Fetch metadata/<uuid>.json from S3
    ├── 2. [Phase 2] SageMaker inference (depth estimation)
    ├── 3. [Phase 3] Bedrock Nova (semantic analysis via main.py)
    ├── 4. [Phase 4] GIS correlation
    └── 5. [Phase 5] Alert generation
```

Phase 1 only uploads; Phases 2–5 are triggered automatically by the event flow above.

## Connection to Main Branch AI

The `main` branch contains:
- `src/pipeline.py` — Fuses Bedrock Nova + YOLOv8 results
- `src/nova_client.py` — Calls Amazon Bedrock for semantic flood analysis
- `src/yolo_detector.py` — Object detection + depth estimation
- `main.py` — CLI entrypoint

Phase 1 media uploads feed directly into this pipeline:

1. PWA uploads `media/<uuid>.mp4` and `metadata/<uuid>.json` to S3
2. EventBridge triggers Step Functions
3. Step Functions invokes a Lambda that calls `src/pipeline.py` with the S3 key
4. Pipeline extracts a frame, runs Nova + YOLO, and outputs structured flood intelligence

The metadata JSON provides geospatial context (`lat`, `lon`, `heading`) that enriches the AI output.

## Production Deployment

### Option A: S3 + CloudFront (Recommended)

```bash
# Upload frontend to an S3 website bucket
aws s3 sync ./frontend s3://floodwatch-pwa-hosting --delete

# Create CloudFront distribution with HTTPS
aws cloudfront create-distribution \
  --origin-domain-name floodwatch-pwa-hosting.s3.amazonaws.com \
  --default-root-object index.html
```

### Option B: Amplify Hosting

```bash
# Install Amplify CLI
npm i -g @aws-amplify/cli

# Initialize and publish
amplify init
amplify add hosting
amplify publish
```

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| GPS denied | `lat` / `lon` stored as `null` |
| Orientation denied | `heading` / `pitch` / `yaw` stored as `null` |
| Offline capture | Saved to IndexedDB, uploaded when online |
| Video >10s | Auto-stopped at 10 seconds |
| Low bandwidth | Exponential backoff retry (5 attempts) |
| Upload interruption | Entry stays in IndexedDB queue, retried |
| Tab closed mid-upload | Background sync resumes on next SW activation |
| No camera available | Placeholder UI shown, graceful degradation |

## Browser Support

| Feature | Chrome | Safari | Firefox | Edge |
|---------|--------|--------|---------|------|
| Service Worker | ✅ | ✅ | ✅ | ✅ |
| Background Sync | ✅ | ❌ | ❌ | ✅ |
| MediaRecorder | ✅ | ✅ (14.3+) | ✅ | ✅ |
| DeviceOrientation | ✅ | ✅ (w/ permission) | ✅ | ✅ |
| IndexedDB | ✅ | ✅ | ✅ | ✅ |

> Background Sync fallback: On browsers without Background Sync support, the PWA retries uploads via the `online` event listener in `app.js`.

## License

Part of the FloodWatch AI disaster intelligence system.
