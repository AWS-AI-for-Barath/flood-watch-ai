export const API_BASE_URL = 'https://150zje9iz6.execute-api.us-east-1.amazonaws.com';

// Fallback mock responses if API fails during local dev (mimics the live backend)
export const apiStore = {
    fetchNearbyAlerts: async (lat: number, lng: number) => {
        // In production, GET /alerts/nearby?lat={lat}&lng={lng}
        // Phase 5 API: the dashboard_api.py returns the recent alerts
        try {
            const res = await fetch(`${API_BASE_URL}/alerts/recent`);
            if (!res.ok) throw new Error("API failed");
            return res.json();
        } catch {
            return [
                { id: "1", severity: "high", alert_message: "High flood risk near Marina Beach", timestamp: new Date().toISOString() },
                { id: "2", severity: "medium", alert_message: "Road blockage at XYZ Street", timestamp: new Date().toISOString() }
            ];
        }
    },

    fetchPredictions: async () => {
        // Phase 4: Mocking what the Lambda returns for Mapbox geojson ingestion
        return {
            type: "FeatureCollection",
            features: [
                {
                    type: "Feature",
                    properties: { severity: "high", submergence_ratio: 0.8 },
                    geometry: {
                        type: "Polygon",
                        coordinates: [[
                            [80.27, 13.08], [80.28, 13.08], [80.28, 13.09], [80.27, 13.09], [80.27, 13.08]
                        ]]
                    }
                }
            ]
        };
    },

    getUploadTokens: async (filename: string, contentType: string) => {
        const res = await fetch(`${API_BASE_URL}/generate-upload-url`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename, contentType })
        });
        if (!res.ok) throw new Error("Upload URL generation failed");
        return res.json();
    }
};
