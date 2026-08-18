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

export function lastModelSegment(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  const bits = value.split("/");
  return (bits[bits.length - 1] || value).trim();
}

/** Short model: last ``/`` segment, optional ``(effort)``. Tooltip is the full name. */
export function formatModelLabel(
  raw: string | null | undefined,
  effort?: string | null,
): { text: string; title: string } {
  const value = (raw || "").trim();
  if (!value) return { text: "-", title: "" };
  const parts = value.split("+").map((s) => s.trim()).filter(Boolean);
  const short = parts.map(lastModelSegment).filter(Boolean);
  let text =
    short.length <= 1 ? short[0] || value : `${short[0]}+...`;
  const extra = (effort || "").trim();
  if (extra) text = `${text} (${extra})`;
  return { text, title: value };
}

export function reasoningEffortFromBinding(binding: unknown): string {
  if (!binding || typeof binding !== "object") return "";
  const rec = binding as Record<string, unknown>;
  const fromOpts = (opts: unknown): string => {
    let raw = opts;
    if (typeof raw === "string" && raw.trim().startsWith("{")) {
      try {
        raw = JSON.parse(raw) as unknown;
      } catch {
        return "";
      }
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "";
    const val = (raw as Record<string, unknown>).reasoning_effort;
    return typeof val === "string" && val.trim() ? val.trim() : "";
  };
  const top = fromOpts(rec.options);
  if (top) return top;
  const ext = rec.extensions;
  if (Array.isArray(ext)) {
    for (const item of ext) {
      if (!item || typeof item !== "object") continue;
      const row = item as Record<string, unknown>;
      if (String(row.plugin || "") === "acp") {
        const hit = fromOpts(row.options);
        if (hit) return hit;
      }
    }
    for (const item of ext) {
      if (!item || typeof item !== "object") continue;
      const hit = fromOpts((item as Record<string, unknown>).options);
      if (hit) return hit;
    }
  }
  return "";
}

export function reasoningEffortFromOverlay(overlay: unknown): string {
  if (!overlay || typeof overlay !== "object") return "";
  const bindings = (overlay as Record<string, unknown>).bindings;
  if (!bindings || typeof bindings !== "object") return "";
  const found: string[] = [];
  for (const raw of Object.values(bindings as Record<string, unknown>)) {
    const effort = reasoningEffortFromBinding(raw);
    if (effort) found.push(effort);
  }
  if (!found.length) return "";
  if (new Set(found).size === 1) return found[0];
  return found.join("+");
}

export function formatBytes(value: number | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return "-";
  if (n < 1024) return `${Math.round(n)} B`;
  const units = ["KB", "MB", "GB"];
  let amount = n / 1024;
  let unit = units[0];
  for (const next of units.slice(1)) {
    if (amount < 1024) break;
    amount /= 1024;
    unit = next;
  }
  const digits = amount < 10 ? 1 : 0;
  return `${amount.toFixed(digits)} ${unit}`;
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
