# AWS Edge Ingestion Pipeline — Phase 1

This guide covers the minimal, production-grade setup for the FloodWatch presigned URL ingestion pipeline using only S3, Lambda, and API Gateway.

## 1. Amazon S3 Configuration

**Bucket Creation:**
1. Go to the S3 Console > **Create bucket**.
2. **Bucket name**: `floodwatch-uploads` (must be globally unique, you might need a suffix).
3. **Object Ownership**: ACLs disabled (recommended).
4. **Block Public Access**: Ensure **Block all public access** is CHECKED.
5. Click **Create bucket**.

**CORS Configuration:**
1. Go to your Bucket > **Permissions** tab > **Cross-origin resource sharing (CORS)**.
2. Edit and add the following JSON:
```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["PUT"],
        "AllowedOrigins": ["*"],
        "ExposeHeaders": []
    }
]
```
*(Note: Replace `*` in `AllowedOrigins` with your frontend domain in production)*

## 2. IAM Role for Lambda (Least Privilege)

1. Go to IAM Console > **Roles** > **Create role**.
2. **Trusted entity type**: AWS service > **Lambda**.
3. Skip attaching managed policies, click **Next**.
4. **Role name**: `FloodWatchLambdaExecutionRole` > **Create role**.
5. Find the newly created role, click **Add permissions** > **Create inline policy**.
6. Switch to JSON editor and paste:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::floodwatch-uploads/*"
        }
    ]
}
```
7. Name the policy `FloodWatchPresignPolicy` and save.

## 3. AWS Lambda Function

1. Go to Lambda Console > **Create function**.
2. **Function name**: `generatePresignedUrl`
3. **Runtime**: Node.js 20.x
4. **Execution role**: Use an existing role > `FloodWatchLambdaExecutionRole`.
5. Click **Create function**.
6. Replace `index.mjs` with the following code (Node.js 20 includes AWS SDK v3 automatically):

```javascript
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const s3Client = new S3Client({ region: process.env.AWS_REGION });
const BUCKET_NAME = process.env.BUCKET_NAME || "floodwatch-uploads";

export const handler = async (event) => {
    try {
        const body = JSON.parse(event.body || "{}");
        const { filename, contentType } = body;

        if (!filename || !contentType) {
            return {
                statusCode: 400,
                headers: getCorsHeaders(),
                body: JSON.stringify({ error: "Missing filename or contentType" })
            };
        }

        // Restrict content types globally
        const allowedTypes = ["video/mp4", "image/jpeg", "image/png"];
        if (!allowedTypes.includes(contentType)) {
            return {
                statusCode: 400,
                headers: getCorsHeaders(),
                body: JSON.stringify({ error: "Invalid content type" })
            };
        }

        const prefix = "media/";
        const key = `${prefix}${filename}`;

        const command = new PutObjectCommand({
            Bucket: BUCKET_NAME,
            Key: key,
            ContentType: contentType
        });

        // 5 minute expiry ensures links aren't stored/reused
        const uploadUrl = await getSignedUrl(s3Client, command, { expiresIn: 300 });

        return {
            statusCode: 200,
            headers: getCorsHeaders(),
            body: JSON.stringify({ uploadUrl, key })
        };
    } catch (error) {
        console.error("Error generating presigned URL:", error);
        return {
            statusCode: 500,
            headers: getCorsHeaders(),
            body: JSON.stringify({ error: "Internal server error" })
        };
    }
};

const getCorsHeaders = () => ({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
});
```
7. Go to **Configuration** > **Environment variables**. Click Edit to add `BUCKET_NAME` = `floodwatch-uploads`.
8. Click **Deploy**.

## 4. API Gateway Configuration

1. Go to API Gateway Console > **Create API** > **HTTP API** (Build).
2. **API name**: `FloodWatchAPI` > Next.
3. Configure routes: Add **POST** `/generate-upload-url`. Next.
4. **Integration mapping**: Connect `/generate-upload-url` to Lambda function `generatePresignedUrl`. Next.
5. Proceed with default stage `$default` > Create.
6. In the left menu of the API, go to **CORS**.
   - **Access-Control-Allow-Origin**: `*`
   - **Access-Control-Allow-Headers**: `content-type`
   - **Access-Control-Allow-Methods**: `POST, OPTIONS`
   - Click **Save**.
7. Copy the **Invoke URL** for your frontend config (e.g. `https://xxxx.execute-api.REGION.amazonaws.com`).

## 5. Client Integration (Frontend App)

### Phase 1: Request Presigned URL
```javascript
const getUploadUrl = async (filename, contentType, apiGatewayUrl) => {
    const response = await fetch(`${apiGatewayUrl}/generate-upload-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, contentType })
    });
    
    if (!response.ok) throw new Error("Failed to get upload URL");
    return await response.json(); // -> { uploadUrl, key }
};
```

### Phase 2: Upload File to S3
```javascript
const uploadMedia = async (presignedUrl, fileBlob, contentType) => {
    // Note: Video duration bounding (e.g., <= 10s) must be checked 
    // locally via loadedmetadata BEFORE reaching this step.
    
    const response = await fetch(presignedUrl, {
        method: "PUT",
        headers: { "Content-Type": contentType },
        body: fileBlob
    });

    if (!response.ok) throw new Error("Upload to S3 failed");
    return true;
};
```

## 6. Testing Instructions

### Step A: Test API Gateway via cURL
Test that Lambda correctly vends a presigned URL:
```bash
curl -X POST https://YOUR_API_ID.execute-api.REGION.amazonaws.com/generate-upload-url \
  -H "Content-Type: application/json" \
  -d '{"filename": "test-vid-123.mp4", "contentType": "video/mp4"}'
```
*Expected Output:*
`{"uploadUrl":"https://floodwatch-uploads.s3.amazonaws.com/media/test-vid-123.mp4?...","key":"media/test-vid-123.mp4"}`

### Step B: Test S3 PUT via cURL
Using the exact `uploadUrl` from Step A:
```bash
curl -X PUT -H "Content-Type: video/mp4" --upload-file ./sample_video.mp4 "https://floodwatch-uploads.s3.amazonaws.com/media/test-vid-123..."
```
*Verify in the AWS S3 Console that `media/test-vid-123.mp4` appears successfully.*
