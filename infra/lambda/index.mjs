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

        // Restrict content types
        const allowedTypes = ["video/mp4", "image/jpeg", "image/png", "application/json"];
        if (!allowedTypes.includes(contentType)) {
            return {
                statusCode: 400,
                headers: getCorsHeaders(),
                body: JSON.stringify({ error: "Invalid content type" })
            };
        }

        // Route to correct S3 prefix based on type
        const prefix = contentType === "application/json" ? "metadata/" : "media/";
        const key = `${prefix}${filename}`;

        const command = new PutObjectCommand({
            Bucket: BUCKET_NAME,
            Key: key,
            ContentType: contentType
        });

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
