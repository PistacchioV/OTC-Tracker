import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Pin the workspace root to this app to avoid Next inferring a parent
  // directory when multiple lockfiles are present.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
