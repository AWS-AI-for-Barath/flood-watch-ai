import { NextResponse } from 'next/server';
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const BUCKET = "floodwatch-uploads";

export async function GET(req: Request) {
    try {
        const s3Client = new S3Client({ region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1" });
        const { searchParams } = new URL(req.url);
        const uuid = searchParams.get('uuid');

        if (!uuid) {
            return NextResponse.json({ error: "Missing uuid parameter" }, { status: 400 });
        }

        // The Bedrock AI Lambda appends the uuid directly
        const analysisKey = `analysis/e2e-${uuid}.json`;

        try {
            const command = new GetObjectCommand({ Bucket: BUCKET, Key: analysisKey });
            const response = await s3Client.send(command);
            const bodyStr = await response.Body?.transformToString();

            if (!bodyStr) {
                return NextResponse.json({ status: "pending" }, { status: 200 });
            }

            const data = JSON.parse(bodyStr);
            return NextResponse.json({ status: "complete", data }, { status: 200 });

        } catch (s3Error: any) {
            if (s3Error.name === "NoSuchKey") {
                // Not ready yet
                return NextResponse.json({ status: "pending" }, { status: 200 });
            }
            throw s3Error;
        }

    } catch (error: any) {
        console.error("Analysis Poll Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
