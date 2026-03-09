"use client";

import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useEffect, useState } from "react";
import { getRecentAlerts } from "@/lib/api";

export function AlertSummaryCard() {
    const [count, setCount] = useState(0);

    useEffect(() => {
        getRecentAlerts().then(res => {
            setCount(res.alerts.length);
        }).catch(() => setCount(0));
    }, []);

    return (
        <Card className="h-full border-yellow-500/50 bg-yellow-500/10 dark:bg-yellow-900/20">
            <CardContent className="flex flex-col items-center justify-center p-4 text-center h-full">
                <AlertTriangle className="w-6 h-6 mb-2 text-yellow-600 dark:text-yellow-500" />
                <p className="text-2xl font-bold leading-none tracking-tight">{count}</p>
                <p className="text-xs text-muted-foreground mt-1">Alerts in area</p>
            </CardContent>
        </Card>
    );
}
