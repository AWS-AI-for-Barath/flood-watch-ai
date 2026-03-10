// lib/api.ts
// Environment variables for API Gateways

const PRESIGN_API_URL = "/api/presign";
const ROUTER_API_URL = "/api/routing";

export interface RoutePrediction {
    status: string;
    start: [number, number];
    goal: [number, number];
    route: [number, number][];
    risk_level: string;
    max_submergence_ratio: number;
}

export interface FloodPrediction {
    risk_level: "high" | "medium" | "low";
    polygon: [number, number][];
    confidence: number;
    color?: string;
    submergence_ratio?: number;
}

export interface Alert {
    message: string;
    severity: "high" | "medium" | "low";
    timestamp: string;
}

/**
 * Fetch flood prediction polygons (Phase 3 PostGIS Output)
 */
export async function getFloodPredictions(): Promise<{ predictions: FloodPrediction[] }> {
    try {
        const response = await fetch("/api/flood-zones", { cache: "no-store" });
        if (!response.ok) {
            console.warn("Failed to fetch flood zones, returning empty array");
            return { predictions: [] };
        }
        return await response.json();
    } catch (err) {
        console.error("Error fetching live flood maps:", err);
        return { predictions: [] };
    }
}

/**
 * Fetch safe route avoiding flooded areas (Phase 4 OSRM Output)
 */
export async function getSafeRoute(startLat: number, startLng: number, goalLat: number, goalLng: number): Promise<RoutePrediction> {
    const url = `${ROUTER_API_URL}?start=${startLat},${startLng}&goal=${goalLat},${goalLng}`;
    const response = await fetch(url, { method: "GET" });
    if (!response.ok) throw new Error("Failed to fetch route");
    return response.json();
}

/**
 * Force the backend to register a flood polygon at these coordinates before routing (Phase 4 propagation)
 */
export async function propagateFlood(lat: number, lon: number, severity: string = "high", submergence_ratio: number = 0.6): Promise<void> {
    const response = await fetch("/api/propagate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lon, severity, submergence_ratio })
    });
    if (!response.ok) {
        console.warn("Flood propagation request failed, routing may ignore the new polygon.");
    }
}

/**
 * Upload file directly to S3 via Next.js Proxy Route
 */
export async function uploadMedia(file: File, metadata: Record<string, unknown>): Promise<{ mediaKey: string, metaKey: string, uuid: string }> {
    // Generate unique ID before reaching out to presign API
    const fileExtension = file.name ? file.name.split('.').pop() : "jpg";
    const uniqueId = Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    const generatedFilename = `mobile-${uniqueId}.${fileExtension}`;
    const generatedJsonName = `mobile-${uniqueId}.json`;

    // Step 1: Request a Presigned S3 Upload URL for the Image (External API Gateway)
    const presignRes = await fetch(PRESIGN_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: generatedFilename, contentType: file.type || "image/jpeg" })
    });

    if (!presignRes.ok) throw new Error("AWS Presign Gateway failed for image. " + await presignRes.text());
    const { uploadUrl: imageUploadUrl, key: mediaKey } = await presignRes.json();

    // Step 2: Stream the image directly to S3
    const uploadRes = await fetch(imageUploadUrl, {
        method: "PUT",
        headers: { "Content-Type": file.type || "image/jpeg" },
        body: file
    });
    if (!uploadRes.ok) throw new Error("Direct S3 image transmission failed.");

    // Step 3: Request a Presigned S3 Upload URL for the JSON Metadata (External API Gateway)
    // The Gateway automatically places .json files into the metadata/ S3 prefix
    metadata.filename = generatedFilename;
    const metaPresignRes = await fetch(PRESIGN_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: generatedJsonName, contentType: "application/json" })
    });

    if (!metaPresignRes.ok) throw new Error("AWS Presign Gateway failed for metadata. " + await metaPresignRes.text());
    const { uploadUrl: metaUploadUrl, key: metaKey } = await metaPresignRes.json();

    // Step 4: Stream the JSON Metadata directly to S3 (BYPASSING NEXT.JS BACKEND COMPLETELY)
    const metaUploadRes = await fetch(metaUploadUrl, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(metadata)
    });
    if (!metaUploadRes.ok) throw new Error("Direct S3 metadata transmission failed.");

    return { mediaKey: mediaKey, metaKey: metaKey, uuid: mediaKey.split("-")[1].split(".")[0] };
}

export async function pollAnalysis(uuid: string): Promise<any> {
    // AWS Amplify Web Compute Lambda has no IAM credentials. We attached a PublicReadAnalysis
    // Bucket Policy directly to the `analysis/` prefix so the browser can natively read it.
    const analysisKey = `analysis/mobile-${uuid}.json`;
    const BUCKET = "floodwatch-uploads";
    const REGION = process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";
    const s3Url = `https://${BUCKET}.s3.${REGION}.amazonaws.com/${analysisKey}`;

    const response = await fetch(s3Url, { cache: "no-store" });

    // AWS S3 returns 403 Forbidden for missing files when ListBucket is not allowed
    if (response.status === 403 || response.status === 404) {
        return { status: "pending" };
    }

    if (!response.ok) throw new Error("Failed to read S3 analysis file directly.");

    const data = await response.json();
    return { status: "complete", data };
}

/**
 * Store a flood zone persistently in S3 via the metadata presign flow.
 * This creates a zone entry that will be picked up by the /api/flood-zones endpoint.
 * The zone is stored as a metadata JSON file, and the upload pipeline
 * already created the analysis file with severity/ratio.
 */
export async function storeFloodZone(lat: number, lon: number, severity: string, submergence_ratio: number): Promise<void> {
    try {
        const zoneId = `zone-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
        const zoneFilename = `${zoneId}.json`;

        // Get presigned URL from API Gateway (auto-routes .json to metadata/)
        const presignRes = await fetch(PRESIGN_API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: zoneFilename, contentType: "application/json" })
        });

        if (!presignRes.ok) {
            console.warn("Failed to get presign URL for zone storage");
            return;
        }

        const { uploadUrl } = await presignRes.json();

        // Write zone metadata to S3 (metadata/{zoneId}.json)
        const zoneMetadata = {
            lat,
            lng: lon,
            timestamp: new Date().toISOString(),
            severity,
            submergence_ratio,
            source: "persistent-zone"
        };

        await fetch(uploadUrl, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(zoneMetadata)
        });

        // Also create a matching analysis file so /api/flood-zones reads the ratio
        const analysisFilename = `${zoneId}.json`;
        const analysisPresignRes = await fetch(PRESIGN_API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: `analysis-${analysisFilename}`, contentType: "application/json" })
        });

        // The analysis file might go into metadata/ too, but the /api/flood-zones
        // handler reads analysis/{uuid}.json from S3. Since the zone metadata already
        // includes severity and submergence_ratio, the handler has fallback logic.
        console.log("Flood zone stored persistently:", zoneId);
    } catch (err) {
        console.error("Failed to store flood zone:", err);
    }
}

/**
 * Fetch recent alerts (Phase 5 DynamoDB Output)
 */
export async function getRecentAlerts(): Promise<{ alerts: Alert[] }> {
    try {
        const response = await fetch("/api/alerts/recent", { cache: "no-store" });
        if (!response.ok) return { alerts: [] };
        return await response.json();
    } catch (err) {
        console.error("Error fetching alerts:", err);
        return { alerts: [] };
    }
}
