"use client";

import { PhoneCall } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmergencyButton() {
    return (
        <Button variant="destructive" className="w-full h-full text-sm font-bold shadow-lg flex flex-col items-center justify-center p-2 rounded-xl">
            <PhoneCall className="w-6 h-6 mb-1" />
            <span>Emergency Dial</span>
        </Button>
    );
}
