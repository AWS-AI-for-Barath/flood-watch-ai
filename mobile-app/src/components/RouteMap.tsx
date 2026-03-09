"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap, Polygon } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { RoutePrediction, getFloodPredictions, FloodPrediction } from "@/lib/api";
import { Card } from "./ui/card";

// Fix for Leaflet default marker icons in Next.js
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-icon-2x.png",
    iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-icon.png",
    shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.3.1/images/marker-shadow.png",
});

function MapController({ route }: { route: [number, number][] }) {
    const map = useMap();
    useEffect(() => {
        if (route && route.length > 0) {
            const bounds = L.latLngBounds(route);
            map.fitBounds(bounds, { padding: [20, 20] });
        }
    }, [route, map]);
    return null;
}

export function RouteMap({ routeData }: { routeData: RoutePrediction }) {
    const [predictions, setPredictions] = useState<FloodPrediction[]>([]);

    useEffect(() => {
        getFloodPredictions().then(res => setPredictions(res.predictions)).catch(console.error);
    }, []);

    if (!routeData || !routeData.route || routeData.route.length === 0) {
        return (
            <Card className="w-full h-full flex items-center justify-center bg-muted/50 border-red-500/50">
                <p className="text-red-500 font-medium text-sm px-4 text-center">No safe route found or area is completely blocked.</p>
            </Card>
        );
    }

    const { route, start, goal, risk_level } = routeData;
    const rl = risk_level?.toLowerCase() || "";
    const isSevere = rl === "high" || rl === "severe" || rl === "critical";
    const isModerate = rl === "medium" || rl === "moderate";
    const routeColor = !isSevere && !isModerate ? "#22c55e" : isModerate ? "#FFD580" : "#ef4444";

    const getPolygonStyle = (level: string) => {
        const l = level?.toLowerCase() || "";
        if (l === "high" || l === "severe" || l === "critical") return { color: "#FF0000", fillColor: "#FF0000", fillOpacity: 0.6 };
        if (l === "medium" || l === "moderate") return { color: "#FF8C00", fillColor: "#FF8C00", fillOpacity: 0.5 };
        return { color: "#FFD700", fillColor: "#FFD700", fillOpacity: 0.4 };
    };

    return (
        <Card className="w-full min-h-[300px] h-full overflow-hidden rounded-xl border-border/50 shadow-sm relative">
            <div className="absolute top-2 left-2 z-[1000] bg-background/90 px-3 py-1.5 rounded-md shadow-sm border text-xs font-bold">
                Risk Level: <span style={{ color: routeColor }} className="capitalize">{risk_level}</span>
            </div>
            <MapContainer
                center={start}
                zoom={13}
                scrollWheelZoom={true}
                className="w-full h-full z-0"
                style={{ height: "100%", width: "100%", minHeight: "350px" }}
                zoomControl={false}
            >
                <MapController route={route} />
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <Marker position={start}>
                    <Popup>Start Location</Popup>
                </Marker>

                <Marker position={goal}>
                    <Popup>Destination</Popup>
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
                                <p>Avoid this area.</p>
                            </div>
                        </Popup>
                    </Polygon>
                ))}

                <Polyline positions={route} pathOptions={{ color: routeColor, weight: 6, opacity: 0.8 }} />
            </MapContainer>
        </Card>
    );
}
