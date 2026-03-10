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
        const metaItems = [];
        while ((match = contentRegex.exec(listXml)) !== null) {
            metaItems.push({ Key: match[1], LastModified: new Date(match[2]) });
        }

        metaItems.sort((a, b) => b.LastModified.getTime() - a.LastModified.getTime());
        const recentItems = metaItems.slice(0, 10);

        const alertsTasks = recentItems.map(async (item) => {
            const uuid = item.Key.replace("metadata/", "").replace(".json", "");
            let ratio = 0.0;
            let severityStr = "low";
            let message = `Automated flood alert dispatched for registered subzone.`;

            try {
                // Fetch metadata (for ratio/severity fallback)
                const metaRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/metadata/${uuid}.json`, { cache: 'no-store' });
                if (metaRes.ok) {
                    const meta = await metaRes.json();
                    ratio = meta.submergence_ratio || 0.0;
                    severityStr = meta.severity || "low";
                    message = `Automated flood alert dispatched for registered subzone.`;
                }

                // Try to fetch analysis file for override (real AI uploads have this)
                const analysisRes = await fetch(`https://${BUCKET}.s3.${REGION}.amazonaws.com/analysis/${uuid}.json`, { cache: 'no-store' });
                if (analysisRes.ok) {
                    const analysis = await analysisRes.json();
                    ratio = analysis.submergence_ratio || ratio;
                    if (ratio >= 0.7) severityStr = "high";
                    else if (ratio >= 0.4) severityStr = "medium";
                    else if (analysis.severity) severityStr = analysis.severity;

                    message = `SYSTEM UPDATE: Live camera feed just detected a ${(ratio * 100).toFixed(1)}% submergence ratio nearby. Proceed with caution.`;
                } else if (ratio > 0) {
                    message = `SYSTEM UPDATE: Live camera feed just detected a ${(ratio * 100).toFixed(1)}% submergence ratio nearby. Proceed with caution.`;
                }
            } catch (e) {
                // Default message
            }

            return {
                id: `live-s3-${uuid}`,
                message: message,
                severity: severityStr,
                timestamp: item.LastModified.toISOString()
            };
        });

        const uniqueAlerts = await Promise.all(alertsTasks);

        // Deduplicate
        const deduped: any[] = [];
        uniqueAlerts.forEach(a => {
            if (!deduped.find(x => x.id === a.id)) {
                deduped.push(a);
            }
        });

        if (deduped.length === 0) {
            deduped.push({
                id: "system-init",
                message: "System initialized. Live flood monitoring actively sensing.",
                severity: "low",
                timestamp: new Date().toISOString()
            });
        }

        return NextResponse.json({ alerts: deduped });
    } catch (error: any) {
        console.error("Alerts API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
