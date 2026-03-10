import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const REGION = process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";

/**
 * GET /api/flood-zones
 * 
 * Returns ALL flood zones by scanning S3 metadata/ and analysis/ prefixes.
 * This replaces the old /api/flood/latest which only returned the single newest upload.
 * 
 * For each metadata file found, it:
 *   1. Reads the metadata (lat/lon)
 *   2. Reads the corresponding analysis file (severity, submergence_ratio)
 *   3. Generates a 32-point circular polygon
 * 
 * Uses ONLY public S3 URLs — no AWS SDK.
 */
export async function GET() {
    try {
        // Step 1: List ALL metadata files from public S3
        const listUrl = `https://${BUCKET}.s3.${REGION}.amazonaws.com/?list-type=2&prefix=metadata/`;
        const listRes = await fetch(listUrl, { cache: 'no-store' });

        if (!listRes.ok) throw new Error(`S3 List Error HTTP ${listRes.status}`);
        const listXml = await listRes.text();

        // Parse XML for Keys and timestamps
        const contentRegex = /<Contents>.*?<Key>(.*?)<\/Key>.*?<LastModified>(.*?)<\/LastModified>.*?<\/Contents>/g;
        let match;
        const metaItems: { Key: string; LastModified: Date }[] = [];
        while ((match = contentRegex.exec(listXml)) !== null) {
            if (match[1].endsWith('.json')) {
                metaItems.push({ Key: match[1], LastModified: new Date(match[2]) });
            }
        }

        if (metaItems.length === 0) {
            return NextResponse.json({ predictions: [] });
        }

        // Sort by most recent, limit to 30 zones
        const recentItems = metaItems
            .sort((a, b) => b.LastModified.getTime() - a.LastModified.getTime())
            .slice(0, 30);

        // Step 2: For each metadata, fetch metadata + analysis in parallel
        const R_EARTH = 111320;
        const zoneTasks = recentItems.map(async (item) => {
            const uuid = item.Key.replace("metadata/", "").replace(".json", "");

            try {
                // Fetch metadata (for lat/lon)
                const metaRes = await fetch(
                    `https://${BUCKET}.s3.${REGION}.amazonaws.com/${item.Key}`,
                    { cache: 'no-store' }
                );
                if (!metaRes.ok) return null;
                const meta = await metaRes.json();

                const lat = meta.lat || null;
                const lng = meta.lng || meta.lon || null;
                if (!lat || !lng) return null; // Skip entries without GPS

                // Use ratio/severity from metadata if present (zone metadata includes them)
                let ratio = meta.submergence_ratio || 0.3;
                let severity = meta.severity || "low";
                let color = "#FFD700";

                // Try to fetch analysis file for override (real AI uploads have this)
                try {
                    const analysisRes = await fetch(
                        `https://${BUCKET}.s3.${REGION}.amazonaws.com/analysis/${uuid}.json`,
                        { cache: 'no-store' }
                    );
                    if (analysisRes.ok) {
                        const analysis = await analysisRes.json();
                        ratio = analysis.submergence_ratio || ratio;
                        severity = analysis.severity || severity;
                    }
                } catch {
                    // Use metadata values as fallback
                }

                // Compute radius from ratio
                let radiusMeters = 50;
                if (ratio < 0.2) {
                    radiusMeters = 50; severity = "low"; color = "#FFD700";
                } else if (ratio < 0.4) {
                    radiusMeters = 120; severity = "low"; color = "#FFD700";
                } else if (ratio < 0.7) {
                    radiusMeters = 300; severity = "medium"; color = "#FF8C00";
                } else {
                    radiusMeters = 600; severity = "high"; color = "#FF0000";
                }

                // Generate 32-point circular polygon
                const points: [number, number][] = [];
                for (let i = 0; i < 32; i++) {
                    const angle = (2 * Math.PI * i) / 32;
                    const dy = radiusMeters * Math.sin(angle);
                    const dx = radiusMeters * Math.cos(angle);
                    const latOffset = dy / R_EARTH;
                    const lonOffset = dx / (R_EARTH * Math.cos(lat * Math.PI / 180));
                    points.push([lat + latOffset, lng + lonOffset]);
                }

                return {
                    zone_id: uuid,
                    risk_level: severity,
                    polygon: points,
                    confidence: 0.95,
                    timestamp: item.LastModified.toISOString(),
                    color: color,
                    submergence_ratio: ratio
                };
            } catch {
                return null;
            }
        });

        const predictions = (await Promise.all(zoneTasks)).filter(Boolean);

        return NextResponse.json({ predictions });

    } catch (error: any) {
        console.error("Flood Zones API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
