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
  ...(basePath ? { basePath } : {}),
};

export default withMDX(config);
