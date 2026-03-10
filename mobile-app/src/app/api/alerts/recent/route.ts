import { NextResponse } from 'next/server';
import aws4 from 'aws4';

export const runtime = 'nodejs';

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const REGION = process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";

// Helper to manually sign and fetch from S3 REST API
async function s3Fetch(path: string, queryParams: string = "") {
    const opts: any = {
        host: `${BUCKET}.s3.${REGION}.amazonaws.com`,
        path: `/${path}${queryParams ? '?' + queryParams : ''}`,
        service: 's3',
        region: REGION,
        method: 'GET',
        headers: {}
    };

    aws4.sign(opts, {
        accessKeyId: process.env.API_AWS_ACCESS_KEY_ID || process.env.AWS_ACCESS_KEY_ID || '',
        secretAccessKey: process.env.API_AWS_SECRET_ACCESS_KEY || process.env.AWS_SECRET_ACCESS_KEY || '',
        sessionToken: process.env.API_AWS_ACCESS_KEY_ID ? undefined : process.env.AWS_SESSION_TOKEN
    });

    const url = `https://${opts.host}${opts.path}`;
    const res = await fetch(url, { method: 'GET', headers: opts.headers, cache: 'no-store' });
    if (!res.ok) throw new Error(`S3 Error HTTP ${res.status}: ${await res.text()}`);
    return res;
}

// Helper to manually sign and fetch from DynamoDB JSON API
async function dynamoScan(tableName: string, limit: number) {
    const bodyStr = JSON.stringify({ TableName: tableName, Limit: limit });
    const opts: any = {
        host: `dynamodb.${REGION}.amazonaws.com`,
        path: '/',
        service: 'dynamodb',
        region: REGION,
        method: 'POST',
        body: bodyStr,
        headers: {
            'Content-Type': 'application/x-amz-json-1.0',
            'X-Amz-Target': 'DynamoDB_20120810.Scan'
        }
    };

    aws4.sign(opts, {
        accessKeyId: process.env.API_AWS_ACCESS_KEY_ID || process.env.AWS_ACCESS_KEY_ID || '',
        secretAccessKey: process.env.API_AWS_SECRET_ACCESS_KEY || process.env.AWS_SECRET_ACCESS_KEY || '',
        sessionToken: process.env.AWS_SESSION_TOKEN || undefined
    });

    const url = `https://${opts.host}${opts.path}`;
    const res = await fetch(url, { method: 'POST', headers: opts.headers, body: bodyStr, cache: 'no-store' });
    if (!res.ok) throw new Error(`DynamoDB Error HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
}

export async function GET() {
    try {
        const response = await dynamoScan("alert_history", 50);
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
            let uuid = null;
            if (items.length > 0) {
                const sortedItems = items.sort((a: any, b: any) => new Date(b.timestamp?.S || 0).getTime() - new Date(a.timestamp?.S || 0).getTime());
                uuid = (sortedItems[0].user_id?.S || sortedItems[0].id?.S || "").replace("live-s3-", "");
            }

            if (uuid) {
                // Fetch the AI Analysis natively from public bucket
                let ratio = 0.0;
                let severityStr = "low";

                const analysisKey = `analysis/${uuid}.json`;
                const analysisRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/${analysisKey}`);
                if (analysisRes.ok) {
                    const analysis = await analysisRes.json();
                    ratio = analysis.submergence_ratio || 0.0;
                    if (ratio >= 0.7) severityStr = "high";
                    else if (ratio >= 0.4) severityStr = "medium";
                }

                // Check metadata for timestamp natively
                let ts = new Date().toISOString();
                try {
                    const metaRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/metadata/${uuid}.json`);
                    if (metaRes.ok) {
                        const metadata = await metaRes.json();
                        if (metadata.timestamp) ts = metadata.timestamp;
                    }
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
