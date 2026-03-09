"use client";
import dynamic from "next/dynamic";
import { LocationCard } from "@/components/LocationCard";
import { AlertSummaryCard } from "@/components/AlertSummaryCard";
import { EmergencyButton } from "@/components/EmergencyButton";

// Leaflet requires window object, so we dynamically import it with SSR disabled
const FloodMap = dynamic(() => import("@/components/FloodMap").then((m) => m.FloodMap), {
  ssr: false,
  loading: () => <div className="w-full h-[400px] rounded-xl bg-muted/50 animate-pulse flex items-center justify-center">Loading Map Engine...</div>
});

export default function HomePage() {
  return (
    <div className="flex flex-col h-full p-4 space-y-4 pt-8">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold tracking-tight">FloodWatch</h1>
        <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse" title="System Live" />
      </div>

      <LocationCard />

      <div className="grid grid-cols-2 gap-4">
        <AlertSummaryCard />
        <EmergencyButton />
      </div>

      <div className="flex-1 min-h-[400px] flex flex-col pt-2">
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 px-1 uppercase tracking-wider">Live Flood Map</h2>
        <FloodMap />
      </div>
    </div>
  );
}
