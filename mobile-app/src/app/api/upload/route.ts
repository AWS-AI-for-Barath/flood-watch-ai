import { NextResponse } from 'next/server';
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { v4 as uuidv4 } from "uuid";

const BUCKET_NAME = process.env.BUCKET_NAME || "floodwatch-uploads";

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
        let formData;
        try {
            formData = await req.formData();
        } catch (e: any) {
            console.error("Failed to parse form data:", e);
            return NextResponse.json({ error: `Form parsing failed: ${e.message}` }, { status: 400 });
        }

        const file = formData.get("file") as File;
        const metadataRaw = formData.get("metadata") as string;

        if (!file) {
            return NextResponse.json({ error: "No file provided in form data" }, { status: 400 });
        }

        let buffer;
        try {
            buffer = Buffer.from(await file.arrayBuffer());
        } catch (e: any) {
            console.error("Failed to extract array buffer from file:", e);
            return NextResponse.json({ error: `File buffer extraction failed: ${e.message}` }, { status: 400 });
        }

        const fileExtension = file.name.split('.').pop() || "jpg";
        const uniqueId = uuidv4().substring(0, 8);
        const mediaKey = `media/e2e-${uniqueId}.${fileExtension}`;
        const metaKey = `metadata/e2e-${uniqueId}.json`;

        // 1. Upload the binary media file directly to S3
        try {
            await s3Client.send(new PutObjectCommand({
                Bucket: BUCKET_NAME,
                Key: mediaKey,
                Body: buffer,
                ContentType: file.type,
            }));
        } catch (e: any) {
            console.error("S3 Media Upload Error:", e);
            return NextResponse.json({ error: `S3 Media PutObject failed: ${e.message}` }, { status: 500 });
        }

        // 2. Upload the associated metadata JSON file
        if (metadataRaw) {
            try {
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
            } catch (e: any) {
                console.error("S3 Metadata Upload Error:", e);
                return NextResponse.json({ error: `S3 Metadata PutObject failed: ${e.message}` }, { status: 500 });
            }
        }

        return NextResponse.json({
            success: true,
            message: "Direct S3 Upload Complete",
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
