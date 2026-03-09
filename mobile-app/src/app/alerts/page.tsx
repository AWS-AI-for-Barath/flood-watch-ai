"use client";

import { useEffect, useState } from "react";
import { getRecentAlerts, Alert } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle, Clock, MapPin } from "lucide-react";

export default function AlertsPage() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getRecentAlerts()
            .then(data => {
                setAlerts(data.alerts || []);
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const getSeverityStyles = (severity: string) => {
        switch (severity.toLowerCase()) {
            case "high": return "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400";
            case "medium": return "border-orange-500/50 bg-orange-500/10 text-orange-700 dark:text-orange-400";
            case "low": return "border-yellow-500/50 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400";
            default: return "border-muted bg-muted text-muted-foreground";
        }
    };

    return (
        <div className="flex flex-col h-full p-4 pt-8 space-y-4">
            <h1 className="text-2xl font-bold tracking-tight">Recent Alerts</h1>

            {loading ? (
                <div className="space-y-3">
                    {[1, 2, 3].map(i => (
                        <Card key={i} className="h-24 animate-pulse bg-muted/40" />
                    ))}
                </div>
            ) : alerts.length === 0 ? (
                <Card className="flex flex-col items-center justify-center p-8 bg-muted/20 text-center">
                    <AlertTriangle className="w-12 h-12 text-muted-foreground mb-4 opacity-50" />
                    <p className="text-muted-foreground">No active alerts in your area.</p>
                </Card>
            ) : (
                <div className="space-y-3 pb-20">
                    {alerts.map((alert, i) => (
                        <Card key={i} className={`border-l-4 ${getSeverityStyles(alert.severity)}`}>
                            <CardContent className="p-4 flex gap-3">
                                <AlertTriangle className="w-6 h-6 shrink-0 mt-1" />
                                <div className="flex-1 space-y-1">
                                    <div className="flex items-start justify-between">
                                        <p className="font-semibold text-sm capitalize">{alert.severity} Risk</p>
                                        <span className="text-[10px] flex items-center opacity-80">
                                            <Clock className="w-3 h-3 mr-1" />
                                            {new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    </div>
                                    <p className="text-sm font-medium leading-tight">{alert.message}</p>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}
