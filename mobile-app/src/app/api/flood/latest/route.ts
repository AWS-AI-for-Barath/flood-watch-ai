import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const REGION = process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";

export async function GET() {
    try {
        const listUrl = `https://${BUCKET}.s3.${REGION}.amazonaws.com/?list-type=2&prefix=metadata/`;
        const listRes = await fetch(listUrl, { cache: 'no-store' });

        if (!listRes.ok) throw new Error(`S3 List Error HTTP ${listRes.status}`);
        const listXml = await listRes.text();

        const contentRegex = /<Contents>.*?<Key>(.*?)<\/Key>.*?<LastModified>(.*?)<\/LastModified>.*?<\/Contents>/g;
        let match;
        const items = [];
        while ((match = contentRegex.exec(listXml)) !== null) {
            items.push({ Key: match[1], LastModified: new Date(match[2]) });
        }

        if (items.length === 0) {
            return NextResponse.json({ features: [] });
        }

        const latestMetaObj = items.sort((a, b) => b.LastModified.getTime() - a.LastModified.getTime())[0];
        const uuid = latestMetaObj.Key.replace("metadata/", "").replace(".json", "");

        let lat = 13.0067;
        let lon = 80.2573;
        let timestamp = new Date().toISOString();

        try {
            const metaRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/${latestMetaObj.Key}`, { cache: 'no-store' });
            if (metaRes.ok) {
                const metadata = await metaRes.json();
                lat = metadata.lat || lat;
                lon = metadata.lng || metadata.lon || lon;
                timestamp = metadata.timestamp || timestamp;
            }
        } catch (e) { console.warn("S3 Meta fetch fail:", e); }

        let ratio = 0.0;
        let severity = "low";
        try {
            const analysisKey = `analysis/${uuid}.json`;
            const analysisRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/${analysisKey}`, { cache: 'no-store' });
            if (analysisRes.ok) {
                const analysis = await analysisRes.json();
                ratio = analysis.submergence_ratio || 0.0;
                severity = analysis.severity || "low";
            }
        } catch (err: any) {
            console.warn("Analysis not found for", uuid, "using defaults");
        }

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

        const clampedRatio = Math.min(1.0, Math.max(0.0, ratio));
        const hue = Math.max(0, 120 - (clampedRatio * 120));
        const color = `hsl(${Math.round(hue)}, 100%, 45%)`;

        const points = [];
        const R_EARTH = 111320;

        for (let i = 0; i < 32; i++) {
            const angle = (2 * Math.PI * i) / 32;
            const dy = radiusMeters * Math.sin(angle);
            const dx = radiusMeters * Math.cos(angle);

            const latOffset = dy / R_EARTH;
            const lonOffset = dx / (R_EARTH * Math.cos(lat * Math.PI / 180));
            points.push([lat + latOffset, lon + lonOffset]);
        }

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
