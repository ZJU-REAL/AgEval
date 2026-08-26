export const appName = "ageval";
export const docsRoute = "/docs";

export const gitConfig = {
  user: "ZJU-REAL",
  repo: "ageval",
  branch: "main",
};

/** Hub SPA origin. Unset = local Vite default; empty string hides the link. */
const DEFAULT_HUB_URL = "http://127.0.0.1:5174";

export function hubSiteUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_HUB_URL;
  if (typeof raw !== "string") return DEFAULT_HUB_URL;
  const value = raw.trim();
  if (!value) return null;
  return value;
}
