"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Polygon, Marker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { getFloodPredictions, FloodPrediction } from "@/lib/api";
import { Card } from "./ui/card";

// Fix for Leaflet default marker icons in Next.js
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-icon-2x.png",
    iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-icon.png",
    shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-shadow.png",
});

function MapController({ center }: { center: [number, number] }) {
    const map = useMap();
    useEffect(() => {
        map.setView(center, 14);
    }, [center, map]);
    return null;
}

export function FloodMap() {
    const [position, setPosition] = useState<[number, number] | null>(null);
    const [predictions, setPredictions] = useState<FloodPrediction[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // 1. Get User Location
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => setPosition([pos.coords.latitude, pos.coords.longitude]),
                () => setPosition([13.0067, 80.2573]) // fallback to Chennai
            );
        } else {
            setPosition([13.0067, 80.2573]);
        }

        // 2. Fetch Flood Polygons (from PostGIS/API wrapper)
        getFloodPredictions().then((res) => {
            setPredictions(res.predictions);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);

    if (!position) {
        return (
            <Card className="w-full h-[300px] flex items-center justify-center bg-muted/50">
                <p className="text-muted-foreground animate-pulse">Initializing map...</p>
            </Card>
        );
    }

    const getPolygonStyle = (level: string) => {
        const l = level?.toLowerCase() || "";
        if (l === "high" || l === "severe" || l === "critical") return { color: "#FF0000", fillColor: "#FF0000", fillOpacity: 0.6 };
        if (l === "medium" || l === "moderate") return { color: "#FF8C00", fillColor: "#FF8C00", fillOpacity: 0.5 };
        return { color: "#FFD700", fillColor: "#FFD700", fillOpacity: 0.4 };
    };

    return (
        <Card className="w-full h-full min-h-[400px] overflow-hidden rounded-xl border-border/50 relative shadow-sm">
            {loading && (
                <div className="absolute inset-0 z-[1000] bg-background/80 flex items-center justify-center backdrop-blur-sm">
                    <p className="font-medium animate-pulse">Loading Live Flood Data...</p>
                </div>
            )}
            <MapContainer
                center={position}
                zoom={14}
                scrollWheelZoom={true}
                className="w-full h-full z-0"
                style={{ height: "100%", width: "100%", minHeight: "350px" }}
                zoomControl={false}
            >
                <MapController center={position} />
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    className="map-tiles"
                />

                {/* User Location Marker */}
                <Marker position={position}>
                    <Popup>You are here</Popup>
                </Marker>

                {/* Flood Risk Polygons */}
                {predictions.map((pred, i) => (
                    <Polygon
                        key={i}
                        positions={pred.polygon}
                        pathOptions={{
                            ...getPolygonStyle(pred.risk_level),
                            weight: 2
                        }}
                    >
                        <Popup>
                            <div className="text-sm">
                                <p className="font-bold capitalize">{pred.risk_level} Risk Zone</p>
                                <p>Confidence: {(pred.confidence * 100).toFixed(0)}%</p>
                            </div>
                        </Popup>
                    </Polygon>
                ))}
            </MapContainer>
        </Card>
    );
}
