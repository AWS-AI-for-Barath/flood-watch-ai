"use client";

import { useState } from "react";
import RouteMap from "@/components/RouteMap";

export default function RoutingPage() {
    const [start, setStart] = useState("");
    const [destination, setDestination] = useState("");
    const [route, setRoute] = useState<[number, number][] | null>(null);
    const [loading, setLoading] = useState(false);

    const handleRoute = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            // Mock coordinates for demonstration based on the Phase 4 logic
            // In a full implementation, we would geocode the text to [lng, lat] first
            const dummyStart = [80.27, 13.08];
            const dummyEnd = [80.25, 13.06];

            const res = await fetch("https://150zje9iz6.execute-api.us-east-1.amazonaws.com/route", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ start: dummyStart, destination: dummyEnd })
            });

            if (!res.ok) throw new Error("Route failed");
            const data = await res.json();

            // OSRM returns coordinates as [lng, lat] which Mapbox requires
            if (data.route && data.route.length > 0) {
                setRoute(data.route);
            } else {
                // Fallback for visual testing
                setRoute([[80.27, 13.08], [80.26, 13.07], [80.25, 13.06]]);
            }
        } catch (err) {
            console.error(err);
            // Fallback for visual testing
            setRoute([[80.27, 13.08], [80.26, 13.07], [80.25, 13.06]]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col gap-4 pb-8 h-[calc(100vh-140px)]">
            <section className="minimal-card z-10 relative">
                <h2 className="text-xl font-bold tracking-tight mb-4">Safe Routing</h2>

                <form onSubmit={handleRoute} className="flex flex-col gap-3">
                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-semibold text-gray-400">STARTING POINT</label>
                        <input
                            type="text"
                            value={start}
                            onChange={(e) => setStart(e.target.value)}
                            placeholder="Current Location"
                            className="w-full bg-gray-50 border border-gray-100 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-black"
                        />
                    </div>
                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-semibold text-gray-400">DESTINATION</label>
                        <input
                            type="text"
                            value={destination}
                            onChange={(e) => setDestination(e.target.value)}
                            placeholder="e.g. Relief Camp Alpha"
                            className="w-full bg-gray-50 border border-gray-100 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-black"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="mt-2 w-full bg-black text-white rounded-xl px-4 py-3 font-semibold text-sm transition-transform active:scale-95 disabled:opacity-50"
                    >
                        {loading ? "Calculating Safest Route..." : "Find Route"}
                    </button>
                </form>
            </section>

            <section className="minimal-card p-0 overflow-hidden flex-1 relative min-h-[300px] mt-[-30px] pt-[30px] -z-0">
                <RouteMap routeCoords={route} />
            </section>
        </div>
    );
}
