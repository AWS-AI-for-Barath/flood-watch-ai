"use client";

import { User, Phone, Globe, LogOut, Settings } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ProfilePage() {
    return (
        <div className="flex flex-col h-full p-4 pt-8 space-y-4">
            <h1 className="text-2xl font-bold tracking-tight">Profile</h1>

            <Card className="border-border/50 shadow-sm">
                <CardContent className="p-6 flex flex-col items-center text-center">
                    <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mb-4">
                        <User className="w-10 h-10 text-primary" />
                    </div>
                    <h2 className="text-xl font-bold">FloodWatch User</h2>
                    <p className="text-sm text-muted-foreground">+91 98765 43210</p>
                </CardContent>
            </Card>

            <Card className="border-border/50 shadow-sm">
                <CardContent className="p-0">
                    <div className="divide-y border-border">

                        <div className="p-4 flex items-center justify-between">
                            <div className="flex items-center gap-3 text-sm font-medium">
                                <Phone className="w-4 h-4 text-muted-foreground" />
                                Emergency Contact
                            </div>
                            <Input className="w-[140px] h-8 text-xs bg-muted/50 border-transparent text-right" placeholder="+91 12345 67890" />
                        </div>

                        <div className="p-4 flex items-center justify-between">
                            <div className="flex items-center gap-3 text-sm font-medium">
                                <Globe className="w-4 h-4 text-muted-foreground" />
                                Language
                            </div>
                            <span className="text-sm text-muted-foreground">English</span>
                        </div>

                        <div className="p-4 flex items-center justify-between">
                            <div className="flex items-center gap-3 text-sm font-medium">
                                <Settings className="w-4 h-4 text-muted-foreground" />
                                Notification Preferences
                            </div>
                            <span className="text-sm text-muted-foreground">SMS & Push</span>
                        </div>

                    </div>
                </CardContent>
            </Card>

            <Button variant="outline" className="w-full mt-auto mb-4 border-red-500/50 text-red-500 hover:bg-red-500/10 hover:text-red-600">
                <LogOut className="w-4 h-4 mr-2" />
                Sign Out
            </Button>
        </div>
    );
}
