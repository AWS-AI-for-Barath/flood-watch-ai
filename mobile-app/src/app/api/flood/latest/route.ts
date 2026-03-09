import { NextResponse } from 'next/server';
import { S3Client, ListObjectsV2Command, GetObjectCommand } from "@aws-sdk/client-s3";

const s3Client = new S3Client({ region: process.env.AWS_REGION || "us-east-1" });
const BUCKET = "floodwatch-uploads";

export async function GET() {
    try {
        // 1. Find the latest metadata file to get the coordinates of the most recent upload
        const listCmd = new ListObjectsV2Command({
            Bucket: BUCKET,
            Prefix: "metadata/"
        });
        const listRes = await s3Client.send(listCmd);

        if (!listRes.Contents || listRes.Contents.length === 0) {
            return NextResponse.json({ features: [] });
        }

        // Sort by LastModified descending
        const latestMetaObj = listRes.Contents.sort((a: any, b: any) => b.LastModified!.getTime() - a.LastModified!.getTime())[0];

        // e.g. metadata/e2e-abc.json
        const uuid = latestMetaObj.Key!.substring("metadata/".length).replace(".json", "");

        // 2. Fetch Metadata (lat, lon, timestamp)
        const metaRes = await s3Client.send(new GetObjectCommand({ Bucket: BUCKET, Key: latestMetaObj.Key }));
        const metaStr = await metaRes.Body?.transformToString();
        const metadata = JSON.parse(metaStr || "{}");
        const lat = metadata.lat || 13.0067;
        const lon = metadata.lng || metadata.lon || 80.2573;
        const timestamp = metadata.timestamp || new Date().toISOString();

        // 3. Fetch corresponding AI Analysis
        let ratio = 0.0;
        let severity = "low";
        try {
            const analysisKey = `analysis/${uuid}.json`;
            const analysisRes = await s3Client.send(new GetObjectCommand({ Bucket: BUCKET, Key: analysisKey }));
            const analysisStr = await analysisRes.Body?.transformToString();
            const analysis = JSON.parse(analysisStr || "{}");
            ratio = analysis.submergence_ratio || 0.0;
            severity = analysis.severity || "low";
        } catch (err: any) {
            console.warn("Analysis not found for", uuid, "using defaults");
        }

        // 4. Compute Radius based on ratio mapping
        let radiusMeters = 50;
        if (ratio < 0.2) {
            radiusMeters = 50;
            severity = "low";
        } else if (ratio < 0.4) {
            radiusMeters = 120;
            severity = "low";
        } else if (ratio < 0.7) {
            radiusMeters = 300;
            severity = "medium";
        } else {
            radiusMeters = 600;
            severity = "high";
        }

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
                    timestamp: timestamp
                }
            ]
        });

    } catch (error: any) {
        console.error("Latest Flood API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
