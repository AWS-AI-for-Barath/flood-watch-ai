import { NextResponse } from 'next/server';
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { v4 as uuidv4 } from "uuid";

const BUCKET_NAME = process.env.BUCKET_NAME || "floodwatch-uploads";


export async function POST(req: Request) {
    try {
        console.log("=== API UPLOAD ROUTE HIT ===");

        let s3Client: S3Client | null = null;
        try {
            s3Client = new S3Client({
                region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1",
            });
        } catch (e: any) {
            console.error("Failed to initialize S3 Client globally:", e);
            return NextResponse.json({ error: "S3 Client failed to initialize on the server: " + e.message }, { status: 500 });
        }

        // Parse the lightweight JSON metadata payload directly to avoid memory/payload limits
        let body;
        try {
            body = await req.json();
            console.log("Parsed JSON body:", Object.keys(body || {}));
        } catch (jsonErr: any) {
            console.error("Failed to parse incoming JSON request:", jsonErr);
            return NextResponse.json({ error: "Invalid JSON payload sent to server" }, { status: 400 });
        }

        const { mediaKey, metadata } = body;

        if (!mediaKey || !metadata) {
            return NextResponse.json({ error: "Missing mediaKey or metadata in payload" }, { status: 400 });
        }

        // Generate the matching metadata key based on the media key e.g "media/e2e-1234.jpg" -> "e2e-1234.json"
        const filename = mediaKey.split('/').pop() || "unknown.jpg";
        const uniqueId = filename.split('.')[0];
        const metaKey = `metadata/${uniqueId}.json`;

        metadata.filename = filename;

        try {
            await s3Client.send(new PutObjectCommand({
                Bucket: BUCKET_NAME,
                Key: metaKey,
                Body: JSON.stringify(metadata),
                ContentType: "application/json",
            }));
        } catch (s3Err: any) {
            console.error("Failed to PutObject to S3:", s3Err);
            return NextResponse.json({ error: "S3 PutObject failed: " + s3Err.message }, { status: 500 });
        }

        return NextResponse.json({
            success: true,
            message: "Metadata Saved Successfully",
            mediaKey,
            metaKey
        }, { status: 200 });

    } catch (criticalError: any) {
        console.error("CRITICAL BOOT ERROR IN UPLOAD ROUTE:", criticalError);
        const errorDetail = criticalError instanceof Error
            ? { name: criticalError.name, message: criticalError.message, stack: criticalError.stack }
            : typeof criticalError === 'object' ? JSON.stringify(criticalError) : String(criticalError);
        return NextResponse.json({ error: "Critical Route Crash: " + JSON.stringify(errorDetail) }, { status: 500 });
    }
}
