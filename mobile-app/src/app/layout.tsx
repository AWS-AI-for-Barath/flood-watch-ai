import type { Metadata, Viewport } from "next";
import { Inter, Geist } from "next/font/google";
import "./globals.css";
import { BottomNav } from "@/components/BottomNav";
import { cn } from "@/lib/utils";

const geist = Geist({ subsets: ['latin'], variable: '--font-sans' });

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FloodWatch Mobile",
  description: "Real-time flood monitoring and routing PWA",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "FloodWatch",
  },
};

export const viewport: Viewport = {
  themeColor: "#020617",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("font-sans", geist.variable)}>
      <body className={`${inter.className} antialiased relative bg-background h-[100dvh] overflow-hidden`}>
        {/* Scrollable Main Area */}
        <main className="h-full w-full overflow-y-auto pb-16">
          {children}
        </main>

        {/* Fixed Navigation */}
        <BottomNav />
      </body>
    </html>
  );
}
