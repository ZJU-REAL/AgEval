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
