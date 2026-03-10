import { NextResponse } from 'next/server';
import aws4 from 'aws4';

export const runtime = 'nodejs';

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const REGION = process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";

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
        sessionToken: process.env.API_AWS_ACCESS_KEY_ID ? undefined : process.env.AWS_SESSION_TOKEN
    });

    const url = `https://${opts.host}${opts.path}`;
    const res = await fetch(url, { method: 'POST', headers: opts.headers, body: bodyStr, cache: 'no-store' });
    if (!res.ok) throw new Error(`DynamoDB Error HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
}

export async function GET() {
    try {
        // 1. Fetch newest alerts from DynamoDB to find the latest valid UUID
        // DynamoDB `aws4` parsing works flawlessly, S3 `aws4` does not.
        const ddbRes = await dynamoScan("alert_history", 20);
        const items = ddbRes.Items || [];

        let uuid = null;
        if (items.length > 0) {
            // Sort to ensure we fetch the newest alert record
            const sortedItems = items.sort((a: any, b: any) => new Date(b.timestamp?.S || 0).getTime() - new Date(a.timestamp?.S || 0).getTime());
            // Most recent UUID is stored as user_id or id in our schema
            uuid = (sortedItems[0].user_id?.S || sortedItems[0].id?.S || "").replace("live-s3-", "");
        }

        // If DB is empty, default to latest known mock
        if (!uuid) {
            uuid = "mobile-1772983173003";
        }

        // 2. Fetch Metadata (lat, lon, timestamp) natively from Public S3
        let lat = 13.0067;
        let lon = 80.2573;
        let timestamp = new Date().toISOString();

        try {
            const metaRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/metadata/${uuid}.json`);
            if (metaRes.ok) {
                const metadata = await metaRes.json();
                lat = metadata.lat || lat;
                lon = metadata.lng || metadata.lon || lon;
                timestamp = metadata.timestamp || timestamp;
            }
        } catch (e) { console.warn("S3 Meta fetch fail:", e); }

        // 3. Fetch corresponding AI Analysis natively from Public S3
        let ratio = 0.0;
        let severity = "low";
        try {
            const analysisKey = `analysis/${uuid}.json`;
            const analysisRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/${analysisKey}`);
            if (analysisRes.ok) {
                const analysis = await analysisRes.json();
                ratio = analysis.submergence_ratio || 0.0;
                severity = analysis.severity || "low";
            }
        } catch (err: any) {
            console.warn("Analysis not found for", uuid, "using defaults");
        }

        // 4. Compute Drastic Radius scaling based on ratio mapping
        let radiusMeters = 100;
        if (ratio < 0.2) {
            radiusMeters = 100;
            severity = "low";
        } else if (ratio < 0.4) {
            radiusMeters = 300;
            severity = "low";
        } else if (ratio < 0.7) {
            radiusMeters = 800;
            severity = "medium";
        } else {
            radiusMeters = 2000;
            severity = "high";
        }

        // 4.5 Compute Spectral Color (Green -> Yellow -> Orange -> Red)
        // Hue 120 is Green, Hue 0 is Red. We interpolate based on ratio.
        const clampedRatio = Math.min(1.0, Math.max(0.0, ratio));
        const hue = Math.max(0, 120 - (clampedRatio * 120));
        const color = `hsl(${Math.round(hue)}, 100%, 45%)`;

        // 5. Generate 32-point circular polygon
        const points = [];
        const R_EARTH = 111320; // meters per degree at equator

        for (let i = 0; i < 32; i++) {
            const angle = (2 * Math.PI * i) / 32;
            const dy = radiusMeters * Math.sin(angle);
            const dx = radiusMeters * Math.cos(angle);

            const latOffset = dy / R_EARTH;
            const lonOffset = dx / (R_EARTH * Math.cos(lat * Math.PI / 180));
            // Leaflet/GeoJSON order convention: [lat, lon] for Leaflet Polygon, but GeoJSON is [lon, lat]
            // We will return [lat, lon] because the frontend expects it for Leaflet Polygon component
            points.push([lat + latOffset, lon + lonOffset]);
        }

        // We return the custom internal structure that 'getFloodPredictions' currently outputs:
        return NextResponse.json({
            predictions: [
                {
                    risk_level: severity,
                    polygon: points,
                    confidence: 0.95,
                    timestamp: timestamp,
                    color: color,
                    submergence_ratio: ratio
                }
            ]
        });

    } catch (error: any) {
        console.error("Latest Flood API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
