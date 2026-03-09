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
    const formData = new FormData();
    formData.append("file", file);
    formData.append("metadata", JSON.stringify(metadata));

    const response = await fetch("/api/upload", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        let errStr = "Failed to upload media";
        try {
            const err = await response.json();
            errStr = err.error || errStr;
        } catch (e) {
            // Server returned a raw 500 string instead of JSON
            const textResponse = await response.text().catch(() => "");
            if (textResponse) errStr = `Server Error: ${textResponse}`;
        }
        throw new Error(errStr);
    }

    let result;
    try {
        result = await response.json();
    } catch (e) {
        throw new Error("Server returned an invalid JSON success response.");
    }

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
