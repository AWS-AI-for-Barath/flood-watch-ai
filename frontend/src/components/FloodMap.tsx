"use client";

import { useEffect, useState } from "react";
import Map, { Source, Layer } from "react-map-gl/mapbox";
import useSWR from "swr";
import { apiStore } from "@/lib/api";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "pk.eyJ1IjoiZHVtbXkiLCJhIjoiZHVtbXkifQ.dummy"; // Replace via env

const floodLayerStyle: any = {
    id: "flood-risk-layer",
    type: "fill",
    paint: {
        "fill-color": [
            "match",
            ["get", "severity"],
            "high", "#ef4444",
            "medium", "#f97316",
            "low", "#eab308",
            "#3b82f6" // default
        ],
        "fill-opacity": 0.5,
    },
};

export default function FloodMap({ lat, lng }: { lat: number; lng: number }) {
    const { data: geojson } = useSWR("predictions", apiStore.fetchPredictions);

    return (
        <div className="absolute inset-0 z-0">
            <Map
                mapboxAccessToken={MAPBOX_TOKEN}
                initialViewState={{
                    longitude: lng,
                    latitude: lat,
                    zoom: 14,
                    pitch: 45,
                }}
                mapStyle="mapbox://styles/mapbox/light-v11"
                interactive={true}
            >
                {geojson && (
                    <Source id="flood-data" type="geojson" data={geojson as any}>
                        <Layer {...floodLayerStyle} />
                    </Source>
                )}
            </Map>
        </div>
    );
}
