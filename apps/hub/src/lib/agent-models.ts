import { encodeDatasetId } from "@/lib/api";

/** Default ``binding.model`` on an ``ageval.agent/1`` package (not identity). */
export function bindingModel(
  binding: Record<string, unknown> | null | undefined,
): string {
  const raw = binding?.model;
  return typeof raw === "string" ? raw.trim() : "";
}

/**
 * Registered models for a harness package: author default, then Performance
 * overlay models, then an unknown ``?model=`` so Leaderboard deep-links still land.
 */
export function registeredModels(
  defaultModel: string,
  performanceModels: Iterable<string | undefined | null>,
  selected?: string | null,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (value: string | undefined | null) => {
    const text = (value || "").trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    out.push(text);
  };
  push(defaultModel);
  for (const item of performanceModels) push(item);
  push(selected);
  return out;
}

/** Hub landing for a harness package. ``model`` is query state, not a route. */
export function agentPackageHref(
  packageId: string,
  model?: string | null,
): string {
  const base = `/agents/${encodeDatasetId(packageId)}`;
  const chosen = (model || "").trim();
  if (!chosen) return base;
  return `${base}?model=${encodeURIComponent(chosen)}`;
}

export function formatAgentRunCommand(
  packageId: string,
  version: string,
  model?: string | null,
  opts?: { builtin?: boolean },
): string {
  const agent = opts?.builtin
    ? `--agent ${packageId}`
    : `--agent ${packageId}@${version.trim() || "<version>"}`;
  const base = `ageval run <dataset> ${agent}`;
  const chosen = (model || "").trim();
  if (!chosen) return base;
  return `${base} --model ${shellToken(chosen)}`;
}

function shellToken(value: string): string {
  if (/^[A-Za-z0-9_./:+-]+$/.test(value)) return value;
  return JSON.stringify(value);
}
