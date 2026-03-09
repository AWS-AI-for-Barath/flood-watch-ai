"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
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


const fetcher = () => getFloodPredictions();

export function FloodMap() {
    const [position, setPosition] = useState<[number, number] | null>(null);

    // Auto-poll the latest flood GeoJSON every 3 seconds
    const { data: res, error } = useSWR('live-flood-map', fetcher, {
        refreshInterval: 3000,
        revalidateOnFocus: true
    });

    const predictions = res?.predictions || [];
    const loading = !res && !error && predictions.length === 0;

    useEffect(() => {
        // 1. Get User Location
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => setPosition([pos.coords.latitude, pos.coords.longitude]),
                () => setPosition([13.0067, 80.2573]) // fallback
            );
        } else {
            setPosition([13.0067, 80.2573]);
        }
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
                {predictions.map((pred, i) => {
                    const defaultStyle = getPolygonStyle(pred.risk_level);
                    const finalColor = pred.color || defaultStyle.color;

                    return (
                        <Polygon
                            key={i}
                            positions={pred.polygon}
                            pathOptions={{
                                color: finalColor,
                                fillColor: finalColor,
                                fillOpacity: 0.5,
                                weight: 2
                            }}
                        >
                            <Popup>
                                <div className="text-sm">
                                    <p className="font-bold capitalize">{pred.risk_level} Risk Zone</p>
                                    <p>Confidence: {(pred.confidence * 100).toFixed(0)}%</p>
                                    {pred.submergence_ratio !== undefined && (
                                        <p>Submergence: {(pred.submergence_ratio * 100).toFixed(1)}%</p>
                                    )}
                                </div>
                            </Popup>
                        </Polygon>
                    );
                })}
            </MapContainer>

            {/* Floating UI Overlay for Submergence Ratio */}
            {predictions.length > 0 && predictions[0].submergence_ratio !== undefined && (
                <div className="absolute top-4 right-4 z-[400] bg-background/90 backdrop-blur pointer-events-none p-3 rounded-lg shadow-sm border border-border flex flex-col items-end">
                    <p className="text-xs text-muted-foreground uppercase font-semibold">Submergence Ratio</p>
                    <p className="text-2xl font-bold font-mono" style={{ color: predictions[0].color }}>
                        {(predictions[0].submergence_ratio * 100).toFixed(1)}%
                    </p>
                </div>
            )}
        </Card>
    );
}
