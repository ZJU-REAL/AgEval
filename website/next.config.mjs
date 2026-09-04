import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** GitHub project pages: `NEXT_PUBLIC_BASE_PATH=/ageval`. Custom domain: unset. */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH?.trim() || "";

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // next dev binds localhost; opening 127.0.0.1 is a different origin and
  // Next 16 blocks /_next/webpack-hmr unless it is listed here.
  allowedDevOrigins: ["127.0.0.1"],
  ...(basePath ? { basePath } : {}),
};

export default withMDX(config);
