import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "mapbox-gl/dist/mapbox-gl.css";
import BottomNavigation from "@/components/BottomNavigation";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "FloodWatch",
  description: "Minimalist community-powered flood intelligence.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "FloodWatch",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased bg-[#f9fafb] min-h-screen pb-[80px]`}>
        <main className="w-full max-w-md mx-auto mt-4 px-4 pt-safe relative isolate flex flex-col gap-4">
          {children}
        </main>
        <BottomNavigation />
      </body>
    </html>
  );
}
