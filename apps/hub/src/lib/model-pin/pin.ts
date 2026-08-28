import pinJson from "./pin.json";

import type { ModelPin } from "./types";

/** Committed snapshot. Missing/invalid pin → empty, never throw. */
export function loadModelPin(): ModelPin {
  const raw = pinJson as Partial<ModelPin>;
  if (!raw || raw.format !== "ageval.model-pin/1") {
    return emptyPin();
  }
  return {
    format: "ageval.model-pin/1",
    source: typeof raw.source === "string" ? raw.source : "",
    pinned_at: typeof raw.pinned_at === "string" ? raw.pinned_at : "",
    labs: raw.labs && typeof raw.labs === "object" ? raw.labs : {},
    models: raw.models && typeof raw.models === "object" ? raw.models : {},
    prefixes: Array.isArray(raw.prefixes) ? raw.prefixes : [],
    lookup: raw.lookup && typeof raw.lookup === "object" ? raw.lookup : {},
    prices: raw.prices && typeof raw.prices === "object" ? raw.prices : {},
    aliases: raw.aliases && typeof raw.aliases === "object" ? raw.aliases : {},
  };
}

export function emptyPin(): ModelPin {
  return {
    format: "ageval.model-pin/1",
    source: "",
    pinned_at: "",
    labs: {},
    models: {},
    prefixes: [],
    lookup: {},
    prices: {},
    aliases: {},
  };
}

export function labLogoSrc(lab: string): string {
  const id = lab.trim();
  if (!id) return "";
  return `/model-pin/logos/${encodeURIComponent(id)}.svg`;
}
