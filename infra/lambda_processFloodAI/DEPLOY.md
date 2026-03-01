# Phase 2: processFloodAI Deployment Guide

## Architecture

```
S3 (media/*) → S3 Event Notification → Lambda (processFloodAI)
                                            ├── Download media from S3
                                            ├── Extract 2–3 frames (ffmpeg)
                                            ├── Invoke Bedrock Nova Lite per frame
                                            ├── Aggregate results (4-key JSON)
                                            └── Write to S3 (analysis/<uuid>.json)
```

---

## Step 1: Enable Bedrock Nova Lite Access

1. Go to **Amazon Bedrock Console** → **Model access** (left sidebar).
2. Click **Manage model access**.
3. Find **Amazon Nova Lite** → check the box → click **Save changes**.
4. Wait for status to show **Access granted**.

---

## Step 2: Create IAM Role

1. Go to **IAM Console** → **Roles** → **Create role**.
2. Trusted entity: **AWS service** → **Lambda**.
3. Skip managed policies → **Next** → Name: `FloodWatchProcessAIRole` → **Create**.
4. Open the role → **Add permissions** → **Create inline policy** → JSON tab.
5. Paste the contents of `infra/lambda_processFloodAI/iam-policy.json`.
6. Name: `FloodWatchProcessAIPolicy` → **Save**.

---

## Step 3: Add ffmpeg Lambda Layer

For video frame extraction, we need ffmpeg available in Lambda.

1. Go to **Lambda Console** → **Layers** → **Create layer**.
2. Use a **public ffmpeg layer ARN** for your region. For **us-east-1**:
   ```
   arn:aws:lambda:us-east-1:188366678178:layer:ffmpeg:1
   ```
   *(This is the commonly used public ffmpeg layer by serverless-community)*

   **Alternative**: If the public layer doesn't work, you can:
   - Download a static ffmpeg binary from https://johnvansickle.com/ffmpeg/
   - Package it into a `.zip` (put binary at `/bin/ffmpeg`)
   - Upload as a custom Lambda Layer
   - Add `/opt/bin` to PATH in Lambda env vars

---

## Step 4: Create Lambda Function

1. Go to **Lambda Console** → **Create function**.
2. **Function name**: `processFloodAI`
3. **Runtime**: Node.js 20.x
4. **Architecture**: x86_64
5. **Execution role**: Use existing → `FloodWatchProcessAIRole`
6. Click **Create function**.

### Configure Settings:
1. **Configuration** → **General configuration** → Edit:
   - Memory: **512 MB**
   - Timeout: **30 seconds**
   - Save.

2. **Configuration** → **Environment variables** → Edit:
   - `BUCKET_NAME` = `floodwatch-uploads`
   - `PATH` = `/opt/bin:/var/lang/bin:/usr/local/bin:/usr/bin:/bin`
   - Save.

3. **Code** tab → **Layers** → **Add a layer**:
   - Choose **Specify an ARN** → paste: `arn:aws:lambda:us-east-1:188366678178:layer:ffmpeg:1`
   - Click **Add**.

4. **Code** tab → Replace `index.mjs` with the contents of:
   `infra/lambda_processFloodAI/index.mjs`

5. Click **Deploy**.

---

## Step 5: Add S3 Trigger

1. In the Lambda function, click **Add trigger**.
2. Source: **S3**.
3. Bucket: `floodwatch-uploads`.
4. Event types: **PUT** (s3:ObjectCreated:Put).
5. Prefix: `media/`
6. Suffix: *(leave empty to match all file types)*
7. Check the acknowledgment box → **Add**.

---

## Step 6: Test

### Quick Test via S3 Console:
1. Go to **S3 Console** → `floodwatch-uploads`.
2. Upload any flood image to `media/test-flood-001.jpg`.
3. Wait ~10 seconds.
4. Check `analysis/test-flood-001.json` — it should contain:
```json
{
  "people_trapped": false,
  "infrastructure_damage": true,
  "severity": "high",
  "submergence_ratio": 0.65
}
```

### Test via Lambda Console:
1. Go to Lambda → `processFloodAI` → **Test** tab.
2. Create test event with this JSON (simulates S3 trigger):
```json
{
  "Records": [
    {
      "s3": {
        "bucket": { "name": "floodwatch-uploads" },
        "object": { "key": "media/test-flood-001.jpg" }
      }
    }
  ]
}
```
3. Click **Test** and check the execution log.

---

## Cost Estimate (100 uploads)

| Resource | Cost |
|----------|------|
| Nova Lite (300 frames × ~80KB) | ~$0.48 |
| Nova Lite output (300 × 120 tokens) | ~$0.04 |
| Lambda (100 × 30s × 512MB) | ~$0.03 |
| S3 operations | ~$0.01 |
| **Total** | **~$0.56** |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ffmpeg not found` | Verify Layer is attached and PATH env var includes `/opt/bin` |
| `AccessDeniedException` on Bedrock | Enable Nova Lite in Bedrock Model Access console |
| `AccessDenied` on S3 | Check IAM policy has correct bucket name and prefixes |
| Timeout | Increase Lambda timeout (max 30s should be sufficient) |
| JSON parse error | Nova may return markdown; the code auto-strips ``` fencing |
