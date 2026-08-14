import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return Number(value).toFixed(2);
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

export function formatTrials(done: number | null | undefined, total: number | null | undefined): string {
  if (total == null) return "-";
  return `${done ?? 0}/${total}`;
}

function parseDisplayDate(iso: string | number | null | undefined): Date | null {
  if (iso == null || iso === "") return null;
  try {
    const d =
      typeof iso === "number"
        ? new Date(iso < 1e12 ? iso * 1000 : iso)
        : new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

export function formatDay(
  iso: string | number | null | undefined,
): string {
  const d = parseDisplayDate(iso);
  if (!d) return iso == null || iso === "" ? "-" : String(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}/${m}/${day}`;
}

export function formatDate(
  iso: string | number | null | undefined,
): string {
  const d = parseDisplayDate(iso);
  if (!d) return iso == null || iso === "" ? "-" : String(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${formatDay(iso)} ${hh}:${mm}`;
}
