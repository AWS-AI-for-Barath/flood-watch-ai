"use client";

import { useState, useEffect } from "react";
import { MapPin } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function LocationCard() {
    const [location, setLocation] = useState<string>("Detecting location...");

    useEffect(() => {
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude } = position.coords;
                    setLocation(`${latitude.toFixed(4)}°N, ${longitude.toFixed(4)}°E`);
                },
                (error) => {
                    setLocation("Location access denied");
                }
            );
        } else {
            setLocation("Geolocation unavailable");
        }
    }, []);

    return (
        <Card className="mb-4">
            <CardContent className="flex items-center p-4">
                <MapPin className="w-5 h-5 mr-3 text-primary" />
                <div>
                    <p className="text-sm text-muted-foreground">Current Location</p>
                    <p className="font-semibold">{location}</p>
                </div>
            </CardContent>
        </Card>
    );
}
