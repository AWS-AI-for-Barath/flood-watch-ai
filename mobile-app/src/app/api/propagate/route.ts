import { NextResponse } from 'next/server';
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { v4 as uuidv4 } from "uuid";

const BUCKET = "floodwatch-uploads";

export async function POST(req: Request) {
    try {
        const lambdaClient = new LambdaClient({ region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1" });
        const s3Client = new S3Client({ region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1" });
        const body = await req.json();
        const lat = parseFloat(body.lat);
        const lon = parseFloat(body.lon);
        const submergence_ratio = parseFloat(body.submergence_ratio || "0.65");
        const severity = body.severity || "high";
        const uuidStr = `ui-manual-${uuidv4().substring(0, 8)}`;

        // 1. Write mock metadata to S3 so Phase 3 knows where it happened
        await s3Client.send(new PutObjectCommand({
            Bucket: BUCKET,
            Key: `metadata/${uuidStr}.json`,
            Body: JSON.stringify({ lat, lon, timestamp: new Date().toISOString() }),
            ContentType: "application/json",
        }));

        // 2. Write mock analysis to S3 so Phase 3 knows the severity
        const analysisKey = `analysis/${uuidStr}.json`;
        await s3Client.send(new PutObjectCommand({
            Bucket: BUCKET,
            Key: analysisKey,
            Body: JSON.stringify({ submergence_ratio, severity, people_trapped: false, infrastructure_damage: true }),
            ContentType: "application/json",
        }));

        // 3. Trigger Phase 3: transformFloodPolygon
        // This lambda reads the S3 files and converts them into a geographic Postgres boundary block
        const phase3Event = {
            Records: [{ s3: { bucket: { name: BUCKET }, object: { key: analysisKey } } }]
        };
        await lambdaClient.send(new InvokeCommand({
            FunctionName: "transformFloodPolygon",
            InvocationType: "RequestResponse",
            Payload: Buffer.from(JSON.stringify(phase3Event)),
        }));

        // 4. Trigger Phase 4: simulateFloodPropagation
        // This lambda calculates the DEM interaction and outputs the block into the routing OSRM layer
        const phase4Resp = await lambdaClient.send(new InvokeCommand({
            FunctionName: "simulateFloodPropagation",
            InvocationType: "RequestResponse",
            Payload: Buffer.from("{}"), // Payloads are ignored; it pulls from Phase 3 db table directly
        }));

        const resultString = Buffer.from(phase4Resp.Payload!).toString();
        const result = JSON.parse(resultString);

        return NextResponse.json(result, { status: 200 });

    } catch (error: any) {
        console.error("Propagation Pipeline Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
