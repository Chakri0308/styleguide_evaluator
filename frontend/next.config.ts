import path from "node:path";
import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Keep SSE streams unbuffered through the proxy.
  compress: false,
  devIndicators: false,
  webpack(config) {
    config.module.rules.push({
      test: /pdfjs-dist[\\/]build[\\/]pdf(\.worker)?(\.min)?\.mjs$/,
      use: [{ loader: path.resolve(__dirname, "pdfjs-loader.cjs") }],
    });
    return config;
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
