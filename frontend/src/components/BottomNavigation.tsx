"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Route, Upload, Bell, User } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const navItems = [
    { href: "/home", label: "Home", icon: Home },
    { href: "/routing", label: "Route", icon: Route },
    { href: "/upload", label: "Upload", icon: Upload },
    { href: "/alerts", label: "Alerts", icon: Bell },
    { href: "/profile", label: "Profile", icon: User },
];

export default function BottomNavigation() {
    const pathname = usePathname();

    return (
        <nav className="fixed bottom-0 left-0 right-0 z-50 flex h-16 w-full max-w-md mx-auto items-center justify-around border-t border-gray-100 bg-gray-50/90 pb-safe backdrop-blur-md">
            {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                    <Link
                        key={item.href}
                        href={item.href}
                        className="flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors"
                    >
                        <div
                            className={cn(
                                "flex items-center justify-center w-12 h-8 rounded-full transition-all duration-300",
                                isActive ? "bg-black text-white" : "bg-transparent text-gray-400 hover:text-black"
                            )}
                        >
                            <Icon size={20} className={isActive ? "stroke-[2.5]" : "stroke-[2]"} />
                        </div>
                    </Link>
                );
            })}
        </nav>
    );
}
