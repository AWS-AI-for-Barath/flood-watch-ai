import { NextResponse } from 'next/server';
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { v4 as uuidv4 } from "uuid";

// Configure AWS S3 Client using the IAM credentials available in the environment
const s3Client = new S3Client({
    region: process.env.AWS_REGION || "us-east-1",
    // Note: In an AWS Amplify deployment, IAM roles provide these credentials automatically.
    // Locally, it will fall back to the ~/.aws/credentials file.
});

const BUCKET_NAME = "floodwatch-uploads";

export async function POST(req: Request) {
    try {
        const formData = await req.formData();
        const file = formData.get("file") as File;
        const metadataRaw = formData.get("metadata") as string;

        if (!file) {
            return NextResponse.json({ error: "No file provided" }, { status: 400 });
        }

        const buffer = Buffer.from(await file.arrayBuffer());
        const fileExtension = file.name.split('.').pop() || "jpg";
        const uniqueId = uuidv4().substring(0, 8);
        const mediaKey = `media/e2e-${uniqueId}.${fileExtension}`;
        const metaKey = `metadata/e2e-${uniqueId}.json`;

        // 1. Upload the binary media file directly to S3
        await s3Client.send(new PutObjectCommand({
            Bucket: BUCKET_NAME,
            Key: mediaKey,
            Body: buffer,
            ContentType: file.type,
        }));

        // 2. Upload the associated metadata JSON file
        if (metadataRaw) {
            const metadata = JSON.parse(metadataRaw);
            // Append the generated filename to metadata as expected by Phase 2
            metadata.filename = `e2e-${uniqueId}.${fileExtension}`;
            metadata.media_type = file.type.startsWith("video") ? "video" : "image";

            await s3Client.send(new PutObjectCommand({
                Bucket: BUCKET_NAME,
                Key: metaKey,
                Body: JSON.stringify(metadata),
                ContentType: "application/json",
            }));
        }

        return NextResponse.json({
            success: true,
            message: "Direct S3 Upload Complete",
            mediaKey,
            metaKey
        }, { status: 200 });

    } catch (error: any) {
        console.error("S3 Upload Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
