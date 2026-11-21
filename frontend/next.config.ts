import type { NextConfig } from "next";

// GITHUB_PAGES=1 builds a static export served from https://<user>.github.io/deepguard-ai/.
const pages = process.env.GITHUB_PAGES === "1";

const nextConfig: NextConfig = pages
  ? { output: "export", basePath: "/deepguard-ai", trailingSlash: true }
  : {};

export default nextConfig;
