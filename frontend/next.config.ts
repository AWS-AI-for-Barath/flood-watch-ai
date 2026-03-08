import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["react-map-gl", "mapbox-gl"],
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  }
};

export default nextConfig;
