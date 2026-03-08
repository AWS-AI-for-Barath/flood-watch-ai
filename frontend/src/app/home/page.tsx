"use client";

import { useEffect, useState } from "react";
import FloodMap from "@/components/FloodMap";
import { apiStore } from "@/lib/api";
import useSWR from "swr";

export default function HomePage() {
    const [loc, setLoc] = useState({ lat: 13.08, lng: 80.27 }); // default Chennai

    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (pos) => setLoc({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
                (err) => console.log(err),
                { enableHighAccuracy: true }
            );
        }
    }, []);

    const { data: alerts } = useSWR(
        loc ? ["alerts", loc.lat, loc.lng] : null,
        ([, lat, lng]) => apiStore.fetchNearbyAlerts(lat, lng)
    );

    return (
        <div className="flex flex-col gap-4 pb-8 h-full">
            {/* 1 & 2. Location & Alert Summary side-by-side */}
            <section className="grid grid-cols-2 gap-4">
                <div className="minimal-card flex flex-col justify-center">
                    <h2 className="text-sm font-semibold tracking-tight text-gray-400 mb-1">LOCATION</h2>
                    <p className="text-xl font-bold text-black tracking-tight leading-none mb-1">Chennai</p>
                    <p className="text-xs text-gray-400 font-mono">{loc.lat.toFixed(4)}, {loc.lng.toFixed(4)}</p>
                </div>

                <div className="minimal-card flex flex-col justify-center">
                    <h2 className="text-sm font-semibold tracking-tight text-gray-400 mb-1">WARNINGS</h2>
                    <div className="flex items-baseline gap-1">
                        <span className="text-3xl font-bold tracking-tighter text-black leading-none py-1">
                            {alerts ? alerts.length : 0}
                        </span>
                        <span className="text-xs text-gray-400">active</span>
                    </div>
                </div>
            </section>

            {/* 3. Emergency Button */}
            <button className="minimal-card flex items-center justify-center gap-2 border-red-100 bg-red-50 text-red-600 transition-transform active:scale-[0.98]">
                <svg className="w-5 h-5 stroke-[2.5]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span className="text-base font-bold tracking-tight">SOS EMERGENCY</span>
            </button>

            {/* 4. Live Map */}
            <section className="minimal-card p-0 overflow-hidden flex-1 min-h-[400px] relative">
                <div className="absolute inset-x-0 top-0 z-10 p-4 pointer-events-none">
                    <div className="bg-white/90 backdrop-blur pb-1 px-3 rounded-full shadow-sm border border-gray-100 inline-block">
                        <span className="text-xs font-semibold tracking-tight">LIVE RISK MAP</span>
                    </div>
                </div>
                <FloodMap lat={loc.lat} lng={loc.lng} />
            </section>
        </div>
    );
}
