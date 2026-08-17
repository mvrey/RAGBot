import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Multi-stage Docker build copies only this self-contained server output,
  // not the full node_modules tree - see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
