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
        let buffer;
        let fileType = "image/jpeg";
        let fileName = "upload.jpg";
        let metadataRaw = "";

        try {
            // In Serverless endpoints, req.formData() crashes if the payload is complex.
            // Using standard req.arrayBuffer() directly works around the Next.js parser crash.
            // Since the frontend sends FormData, we have to parse the multipart boundary boundaries manually.
            const contentType = req.headers.get("content-type") || "";
            if (!contentType.includes("multipart/form-data")) {
                return NextResponse.json({ error: "Invalid content type: " + contentType }, { status: 400 });
            }

            // To avoid complex multipart manual parsing in AWS edge without busboy streaming issues,
            // we will simply read the raw formData if it's small enough, otherwise we fallback.
            // Let's try FormData one last time with correct await and catch.
            const formData = await req.formData();

            const file = formData.get("file") as File;
            metadataRaw = formData.get("metadata") as string;

            if (!file) {
                return NextResponse.json({ error: "No file provided" }, { status: 400 });
            }

            buffer = Buffer.from(await file.arrayBuffer());
            fileType = file.type;
            fileName = file.name || "upload.jpg";

        } catch (e: any) {
            console.error("Payload extraction failed completely:", e);
            return NextResponse.json({ error: `Payload extraction failed. The file may be too large for Amplify Web Compute limitations: ${e.message}` }, { status: 413 });
        }

        const fileExtension = fileName.split('.').pop() || "jpg";
        const uniqueId = uuidv4().substring(0, 8);
        const mediaKey = `media/e2e-${uniqueId}.${fileExtension}`;
        const metaKey = `metadata/e2e-${uniqueId}.json`;

        // 1. Upload the binary media file directly to S3
        try {
            await s3Client.send(new PutObjectCommand({
                Bucket: BUCKET_NAME,
                Key: mediaKey,
                Body: buffer,
                ContentType: fileType,
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
                metadata.media_type = fileType.startsWith("video") ? "video" : "image";

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
