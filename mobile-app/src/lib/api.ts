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
        const response = await fetch("/api/flood/latest", { cache: "no-store" });
        if (!response.ok) {
            console.warn("Failed to fetch latest flood GeoJSON, returning empty array");
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
    // Generate unique ID before reaching out to presign API to avoid AWS overwriting the same `upload.jpg`
    const fileExtension = file.name ? file.name.split('.').pop() : "jpg";
    const uniqueId = Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    const generatedFilename = `mobile-${uniqueId}.${fileExtension}`;

    // Step 1: Request a Presigned S3 Upload URL from the API Gateway
    const presignRes = await fetch(PRESIGN_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: generatedFilename, contentType: file.type || "image/jpeg" })
    });

    if (!presignRes.ok) {
        throw new Error("Failed to secure an AWS S3 upload token. " + await presignRes.text());
    }

    const { uploadUrl, key } = await presignRes.json();
    if (!uploadUrl || !key) {
        throw new Error("AWS did not return a valid presigned upload URL.");
    }

    // Step 2: Stream the heavy binary file directly from the browser to S3 (Bypassing Next.js Lambdas!)
    const uploadRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": file.type || "image/jpeg" },
        body: file
    });

    if (!uploadRes.ok) {
        throw new Error("Direct S3 transmission failed. Please try again.");
    }

    // Step 3: Tell Next.js to save the lightweight Metadata JSON
    const metaRes = await fetch("/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mediaKey: key, metadata })
    });

    if (!metaRes.ok) {
        let errStr = "Failed to save media metadata";
        const textResponse = await metaRes.text();
        try {
            const err = JSON.parse(textResponse);
            errStr = err.error || errStr;
        } catch (e) {
            if (textResponse) errStr = `Server Error: ${textResponse}`;
        }
        throw new Error(errStr);
    }

    const result = await metaRes.json();
    return { mediaKey: result.mediaKey, metaKey: result.metaKey, uuid: result.mediaKey.split("-")[1].split(".")[0] };
}

/**
 * Poll S3 for the asynchronous Bedrock AI analysis file
 */
export async function pollAnalysis(uuid: string): Promise<any> {
    const response = await fetch(`/api/analysis?uuid=${uuid}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Failed to check analysis");
    return response.json();
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
