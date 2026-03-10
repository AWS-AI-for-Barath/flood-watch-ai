import { NextResponse } from 'next/server';
import { DynamoDBClient, ScanCommand } from "@aws-sdk/client-dynamodb";
import { S3Client, ListObjectsV2Command, GetObjectCommand } from "@aws-sdk/client-s3";

export const runtime = 'nodejs';

const BUCKET = "floodwatch-uploads";

export async function GET() {
    try {
        const credentials = {
            accessKeyId: process.env.API_AWS_ACCESS_KEY_ID || process.env.AWS_ACCESS_KEY_ID || "",
            secretAccessKey: process.env.API_AWS_SECRET_ACCESS_KEY || process.env.AWS_SECRET_ACCESS_KEY || ""
        };
        const ddbClient = new DynamoDBClient({
            region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1",
            credentials
        });
        const s3Client = new S3Client({
            region: process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1",
            credentials
        });
        const command = new ScanCommand({
            TableName: "alert_history",
            Limit: 50
        });

        const response = await ddbClient.send(command);
        const items = response.Items || [];

        // Convert from DynamoDB format to simple JSON expected by frontend Alert interface
        const alerts: any[] = items.map((item: any) => ({
            id: item.user_id?.S || item.id?.S || Math.random().toString(),
            message: item.message?.S || `Flood alert dispatched for ${item.severity?.S || 'unknown'} severity level in your registered subzone.`,
            severity: item.severity?.S || "medium",
            timestamp: item.timestamp?.S || new Date().toISOString()
        }));

        // Sort descending by timestamp
        alerts.sort((a: any, b: any) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

        // Deduplicate messages since we send alerts to multiple users simultaneously for the same event
        const uniqueAlerts: any[] = [];
        const seenKeys = new Set();
        for (const alert of alerts) {
            const tsDate = new Date(alert.timestamp);
            const key = `${tsDate.getUTCFullYear()}-${tsDate.getUTCMonth()}-${tsDate.getUTCDate()}-${tsDate.getUTCHours()}-${alert.severity}`;
            if (!seenKeys.has(key)) {
                seenKeys.add(key);
                uniqueAlerts.push(alert);
            }
        }

        // --- NEW: Inject the latest Live S3 Analysis as the newest alert ---
        try {
            const listCmd = new ListObjectsV2Command({ Bucket: BUCKET, Prefix: "metadata/" });
            const listRes = await s3Client.send(listCmd);

            if (listRes.Contents && listRes.Contents.length > 0) {
                // Get the absolute newest uploaded image metadata
                const latestMetaObj = listRes.Contents.sort((a: any, b: any) => b.LastModified!.getTime() - a.LastModified!.getTime())[0];
                const uuid = latestMetaObj.Key!.substring("metadata/".length).replace(".json", "");

                // Fetch the AI Analysis for it
                const analysisKey = `analysis/${uuid}.json`;
                const analysisRes = await s3Client.send(new GetObjectCommand({ Bucket: BUCKET, Key: analysisKey }));
                const analysisStr = await analysisRes.Body?.transformToString();
                const analysis = JSON.parse(analysisStr || "{}");

                const ratio = analysis.submergence_ratio || 0.0;
                let severityStr = "low";
                if (ratio >= 0.7) severityStr = "high";
                else if (ratio >= 0.4) severityStr = "medium";

                // Check metadata for timestamp
                let ts = new Date().toISOString();
                try {
                    const metaRes = await s3Client.send(new GetObjectCommand({ Bucket: BUCKET, Key: latestMetaObj.Key }));
                    const metaStr = await metaRes.Body?.transformToString();
                    const metadata = JSON.parse(metaStr || "{}");
                    if (metadata.timestamp) ts = metadata.timestamp;
                } catch (e) { }

                // Prepend the real-time alert
                uniqueAlerts.unshift({
                    id: `live-s3-${uuid}`,
                    message: `SYSTEM UPDATE: Live camera feed just detected a ${(ratio * 100).toFixed(1)}% submergence ratio nearby. Proceed with caution.`,
                    severity: severityStr,
                    timestamp: ts
                });
            }
        } catch (s3Err) {
            console.error("Failed to fetch Live S3 alert:", s3Err);
        }

        return NextResponse.json({ alerts: uniqueAlerts.slice(0, 10) });
    } catch (error: any) {
        console.error("Alerts API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
