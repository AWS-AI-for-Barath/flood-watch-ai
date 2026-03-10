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

    if (!res.ok) {
        throw new Error(`S3 Error HTTP ${res.status}: ${await res.text()}`);
    }
    return res;
}

export async function GET() {
    try {
        // 1. Find the latest metadata file natively via S3 REST API
        // ListObjectsV2 requires ?list-type=2&prefix=metadata/
        const listRes = await s3Fetch("", "list-type=2&prefix=metadata/");
        const listXml = await listRes.text();

        // Simple regex XML parsing to avoid large dependency just for getting Keys
        // Example XML: <Contents><Key>metadata/mobile-abc.json</Key><LastModified>2026...</LastModified></Contents>
        const contentRegex = /<Contents>.*?<Key>(.*?)<\/Key>.*?<LastModified>(.*?)<\/LastModified>.*?<\/Contents>/g;
        let match;
        const items = [];
        while ((match = contentRegex.exec(listXml)) !== null) {
            items.push({ Key: match[1], LastModified: new Date(match[2]) });
        }

        if (items.length === 0) {
            return NextResponse.json({ features: [] });
        }

        // Sort by LastModified descending
        const latestMetaObj = items.sort((a, b) => b.LastModified.getTime() - a.LastModified.getTime())[0];

        // e.g. metadata/mobile-123.json
        const uuid = latestMetaObj.Key.substring("metadata/mobile-".length).replace(".json", "");

        // 2. Fetch Metadata (lat, lon, timestamp) natively
        const metaRes = await s3Fetch(latestMetaObj.Key);
        const metadata = await metaRes.json();
        const lat = metadata.lat || 13.0067;
        const lon = metadata.lng || metadata.lon || 80.2573;
        const timestamp = metadata.timestamp || new Date().toISOString();

        // 3. Fetch corresponding AI Analysis natively from the public bucket
        let ratio = 0.0;
        let severity = "low";
        try {
            const analysisKey = `analysis/mobile-${uuid}.json`;
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
