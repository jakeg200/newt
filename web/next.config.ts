import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A separate output folder lets a production build run while the dev server is up.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
