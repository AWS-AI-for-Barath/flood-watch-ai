"use client";

import { useEffect, useState } from "react";
import Map, { Source, Layer } from "react-map-gl/mapbox";
import useSWR from "swr";
import { apiStore } from "@/lib/api";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "pk.eyJ1IjoiZHVtbXkiLCJhIjoiZHVtbXkifQ.dummy";

const routeLayerStyle: any = {
    id: "safe-route-layer",
    type: "line",
    paint: {
        "line-color": "#2563eb", // blue-600
        "line-width": 4,
    },
};

export default function RouteMap({ routeCoords }: { routeCoords: [number, number][] | null }) {
    const geojson: any = routeCoords ? {
        type: "Feature",
        properties: {},
        geometry: {
            type: "LineString",
            coordinates: routeCoords,
        },
    } : null;

    return (
        <div className="absolute inset-0 z-0">
            <Map
                mapboxAccessToken={MAPBOX_TOKEN}
                initialViewState={{
                    longitude: routeCoords?.[0]?.[0] || 80.27,
                    latitude: routeCoords?.[0]?.[1] || 13.08,
                    zoom: 13,
                }}
                mapStyle="mapbox://styles/mapbox/light-v11"
                interactive={true}
            >
                {geojson && (
                    <Source id="route-data" type="geojson" data={geojson}>
                        <Layer {...routeLayerStyle} />
                    </Source>
                )}
            </Map>
        </div>
    );
}
