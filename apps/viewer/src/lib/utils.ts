import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return Number(value).toFixed(2);
}

/** Coerce API error fields to a string for React children (objects crash React #31). */
export function formatError(value: unknown): string {
  if (value == null || value === "") return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function formatTrials(done: number | null | undefined, total: number | null | undefined): string {
  if (total == null) return "-";
  return `${done ?? 0}/${total}`;
}

/** Jobs / Hub axis: ``a+b+c`` → ``a+...``; tooltip keeps the full string. */
export function formatAxisLabel(raw: string | null | undefined): {
  text: string;
  title?: string;
} {
  const value = (raw || "").trim();
  if (!value) return { text: "-" };
  const parts = value.split("+").map((s) => s.trim()).filter(Boolean);
  if (parts.length <= 1) return { text: value, title: value };
  return { text: `${parts[0]}+...`, title: parts.join("+") };
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${y}/${m}/${day} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}
