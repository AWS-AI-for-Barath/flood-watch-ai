"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Map as MapIcon, Camera, Bell, User } from "lucide-react";
import { cn } from "@/lib/utils"; // Assumes ShadCN's cn is configured

const tabs = [
    { name: "Home", href: "/", icon: Home },
    { name: "Routing", href: "/routing", icon: MapIcon },
    { name: "Upload", href: "/upload", icon: Camera },
    { name: "Alerts", href: "/alerts", icon: Bell },
    { name: "Profile", href: "/profile", icon: User },
];

export function BottomNav() {
    const pathname = usePathname();

    return (
        <div className="fixed bottom-0 left-0 z-50 w-full h-16 bg-background border-t">
            <div className="grid h-full max-w-lg grid-cols-5 mx-auto font-medium">
                {tabs.map((tab) => {
                    const isActive = pathname === tab.href;
                    const Icon = tab.icon;
                    return (
                        <Link
                            key={tab.name}
                            href={tab.href}
                            className={cn(
                                "inline-flex flex-col items-center justify-center px-5 hover:bg-muted/50 transition-colors",
                                isActive ? "text-primary" : "text-muted-foreground"
                            )}
                        >
                            <Icon className="w-6 h-6 mb-1" />
                            <span className="text-[10px]">{tab.name}</span>
                        </Link>
                    );
                })}
            </div>
        </div>
    );
}
