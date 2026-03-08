"use client";

import useSWR from "swr";
import { apiStore } from "@/lib/api";
import { AlertTriangle, Info, ShieldAlert } from "lucide-react";
import { clsx } from "clsx";

const getSeverityStyles = (severity: string) => {
    switch (severity) {
        case "high": return { border: "border-red-500", bg: "bg-red-50", icon: ShieldAlert, color: "text-red-500" };
        case "medium": return { border: "border-orange-400", bg: "bg-orange-50", icon: AlertTriangle, color: "text-orange-500" };
        default: return { border: "border-yellow-400", bg: "bg-yellow-50", icon: Info, color: "text-yellow-600" };
    }
};

export default function AlertsPage() {
    const { data: alerts, isValidating } = useSWR("alerts", () => apiStore.fetchNearbyAlerts(13.08, 80.27));

    return (
        <div className="flex flex-col gap-6 pb-8">
            <div className="px-2 pt-2">
                <h1 className="text-3xl font-bold tracking-tight">Active Alerts</h1>
                <p className="text-sm text-gray-500 mt-1">Real-time emergency notifications.</p>
            </div>

            <div className="flex flex-col gap-3">
                {isValidating && !alerts && <p className="text-sm text-gray-400 ml-2">Syncing...</p>}
                {alerts?.length === 0 && <p className="text-sm text-gray-400 ml-2">No active alerts for your area.</p>}

                {alerts?.map((alert: any, i: number) => {
                    const style = getSeverityStyles(alert.severity);
                    const Icon = style.icon;
                    const time = new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                    return (
                        <div key={i} className={clsx("minimal-card border-l-4 p-4", style.border)}>
                            <div className="flex items-start justify-between">
                                <div className="flex gap-3">
                                    <div className={clsx("p-2 rounded-full", style.bg, style.color)}>
                                        <Icon size={20} strokeWidth={2.5} />
                                    </div>
                                    <div>
                                        <span className={clsx("text-xs font-bold uppercase tracking-wider mb-1 block", style.color)}>
                                            {alert.severity} RISK
                                        </span>
                                        <p className="text-sm font-semibold text-black leading-snug">
                                            {alert.alert_message}
                                        </p>
                                    </div>
                                </div>
                                <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{time}</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
