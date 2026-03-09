"use client";

import { useState, useEffect } from "react";
import { getSafeRoute, propagateFlood, RoutePrediction } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { MapPin, Navigation, Loader2 } from "lucide-react";
import dynamic from "next/dynamic";

const RouteMap = dynamic(() => import("@/components/RouteMap").then(m => m.RouteMap), { ssr: false });

export default function RoutingPage() {
    const [startLat, setStartLat] = useState("13.0067");
    const [startLng, setStartLng] = useState("80.2573");
    const [goalLat, setGoalLat] = useState("13.0827");
    const [goalLng, setGoalLng] = useState("80.2707");
    const [loading, setLoading] = useState(false);
    const [routeData, setRouteData] = useState<RoutePrediction | null>(null);
    const [error, setError] = useState("");

    // Hydrate start coordinates from recent upload if available
    useEffect(() => {
        const savedLat = localStorage.getItem("floodwatch_last_upload_lat");
        const savedLng = localStorage.getItem("floodwatch_last_upload_lng");
        if (savedLat && savedLng) {
            setStartLat(savedLat);
            setStartLng(savedLng);
        }
    }, []);

    const handleRoute = async () => {
        setLoading(true);
        setError("");
        try {
            // Read the real AI values from the Upload flow
            const savedRatioStr = localStorage.getItem("floodwatch_last_ratio") || "0.6";
            const savedRatio = parseFloat(savedRatioStr);

            let severity = "high";
            if (savedRatio < 0.4) severity = "low";
            else if (savedRatio < 0.7) severity = "medium";

            // 1. Force Backend to register this exact start location as a deterministic severity flood polygon
            await propagateFlood(parseFloat(startLat), parseFloat(startLng), severity, savedRatio);

            // 2. Fetch the safe route which will now avoid the newly propagated polygon
            const data = await getSafeRoute(parseFloat(startLat), parseFloat(startLng), parseFloat(goalLat), parseFloat(goalLng));
            setRouteData(data);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed to find route");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col min-h-full overflow-y-auto pb-24 p-4 pt-8 space-y-4">
            <h1 className="text-2xl font-bold tracking-tight">Safe Routing</h1>

            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Navigation Coordinates</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase flex items-center"><MapPin className="w-3 h-3 mr-1" /> Start Lat</label>
                            <Input value={startLat} onChange={e => setStartLat(e.target.value)} placeholder="13.04" className="h-8 text-sm" />
                        </div>
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase">Start Lng</label>
                            <Input value={startLng} onChange={e => setStartLng(e.target.value)} placeholder="80.23" className="h-8 text-sm" />
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase flex items-center"><Navigation className="w-3 h-3 mr-1" /> Dest Lat</label>
                            <Input value={goalLat} onChange={e => setGoalLat(e.target.value)} placeholder="13.09" className="h-8 text-sm" />
                        </div>
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase">Dest Lng</label>
                            <Input value={goalLng} onChange={e => setGoalLng(e.target.value)} placeholder="80.21" className="h-8 text-sm" />
                        </div>
                    </div>
                    <div className="pt-4 pb-1">
                        <Button onClick={handleRoute} disabled={loading} size="lg" className="w-full font-bold shadow-md">
                            {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {loading ? "Simulating Flood Propagation..." : "Find Safe Route"}
                        </Button>
                        {error && <p className="text-red-500 font-medium text-xs mt-2 text-center">{error}</p>}
                    </div>
                </CardContent>
            </Card>

            <div className="flex-1 min-h-[350px] flex flex-col pt-2">
                <h2 className="text-sm font-semibold text-muted-foreground mb-3 px-1 uppercase tracking-wider">Route Map</h2>
                {routeData ? (
                    <RouteMap routeData={routeData} />
                ) : (
                    <Card className="flex-1 flex items-center justify-center bg-muted/20">
                        <p className="text-sm text-muted-foreground text-center px-4">Enter coordinates and tap &quot;Find Safe Route&quot; to display OSRM path avoiding floods.</p>
                    </Card>
                )}
            </div>
        </div>
    );
}
