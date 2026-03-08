"use client";

import { UserCircle, Settings, Phone, Globe, LogOut } from "lucide-react";

export default function ProfilePage() {
    return (
        <div className="flex flex-col gap-6 pb-8 h-full">
            <div className="flex items-center gap-4 px-2 pt-4 pb-2">
                <UserCircle size={64} className="text-gray-200" strokeWidth={1} />
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">John Doe</h1>
                    <p className="text-sm font-medium text-gray-400">+1 234 567 8900</p>
                </div>
            </div>

            <section className="minimal-card flex flex-col gap-0 p-0 overflow-hidden divide-y divide-gray-50">
                <button className="flex items-center gap-3 px-5 py-4 w-full text-left active:bg-gray-50 transition-colors">
                    <Globe size={20} className="text-gray-400" />
                    <div className="flex-1">
                        <span className="text-sm font-semibold">Language Priority</span>
                        <p className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">English, Tamil</p>
                    </div>
                </button>

                <button className="flex items-center gap-3 px-5 py-4 w-full text-left active:bg-gray-50 transition-colors">
                    <Phone size={20} className="text-gray-400" />
                    <div className="flex-1">
                        <span className="text-sm font-semibold">Emergency Contacts</span>
                        <p className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">2 ICE Numbers</p>
                    </div>
                </button>

                <button className="flex items-center gap-3 px-5 py-4 w-full text-left active:bg-gray-50 transition-colors">
                    <Settings size={20} className="text-gray-400" />
                    <div className="flex-1">
                        <span className="text-sm font-semibold">Preferences</span>
                        <p className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">Notifications, Layout</p>
                    </div>
                </button>
            </section>

            <div className="mt-auto pt-8">
                <button className="flex items-center justify-center gap-2 w-full px-4 py-4 rounded-[20px] bg-gray-50 text-red-500 font-semibold text-sm active:scale-95 transition-transform">
                    <LogOut size={16} className="stroke-[2.5]" />
                    Sign Out
                </button>
            </div>
        </div>
    );
}
