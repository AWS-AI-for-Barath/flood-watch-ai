import { NextResponse } from 'next/server';
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { v4 as uuidv4 } from "uuid";

const BUCKET_NAME = process.env.BUCKET_NAME || "floodwatch-uploads";

export const config = {
    api: {
        bodyParser: false,
    },
};

export async function POST(req: Request) {
    let s3Client: S3Client | null = null;
    try {
        s3Client = new S3Client({
            region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1",
        });
    } catch (e: any) {
        console.error("Failed to initialize S3 Client globally:", e);
        return NextResponse.json({ error: "S3 Client failed to initialize on the server: " + e.message }, { status: 500 });
    }

    try {
        // Parse the lightweight JSON metadata payload directly to avoid memory/payload limits
        const body = await req.json();
        const { mediaKey, metadata } = body;

        if (!mediaKey || !metadata) {
            return NextResponse.json({ error: "Missing mediaKey or metadata in payload" }, { status: 400 });
        }

        // Generate the matching metadata key based on the media key e.g "media/e2e-1234.jpg" -> "e2e-1234.json"
        const filename = mediaKey.split('/').pop() || "unknown.jpg";
        const uniqueId = filename.split('.')[0];
        const metaKey = `metadata/${uniqueId}.json`;

        metadata.filename = filename;

        await s3Client.send(new PutObjectCommand({
            Bucket: BUCKET_NAME,
            Key: metaKey,
            Body: JSON.stringify(metadata),
            ContentType: "application/json",
        }));

        return NextResponse.json({
            success: true,
            message: "Metadata Saved Successfully",
            mediaKey,
            metaKey
        }, { status: 200 });

    } catch (error: any) {
        console.error("Global Catch Error:", error);
        const errorDetail = error instanceof Error
            ? { name: error.name, message: error.message, stack: error.stack }
            : typeof error === 'object' ? JSON.stringify(error) : String(error);
        return NextResponse.json({ error: "S3 Upload Error: " + JSON.stringify(errorDetail) }, { status: 500 });
    }
}
