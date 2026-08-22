import {
  BRAND_MARK_IDS,
  matchBrandMarkExact,
  matchBrandMarkToken,
} from "@/lib/brand-marks/catalog";

export type EntityMarkHint = {
  iconKey?: string | null;
  packageId?: string | null;
  displayName?: string | null;
  slots?: string[];
  entry?: string | null;
  executor?: string | null;
  model?: string | null;
};

export type ResolvedMark = {
  key: string | null;
  letter: string;
};

function firstLetter(raw: string): string {
  const ch = [...raw].find((c) => /[a-z0-9]/i.test(c));
  return (ch || "?").toUpperCase();
}

function packageParts(id: string): string[] {
  return id
    .split("/")
    .map((p) => p.trim())
    .filter(Boolean);
}

export function resolveEntityMark(hint: EntityMarkHint): ResolvedMark {
  const stored = (hint.iconKey || "").trim().toLowerCase();
  if (stored && BRAND_MARK_IDS.has(stored)) {
    return { key: stored, letter: firstLetter(stored) };
  }

  const exactSources = [
    ...packageParts(hint.packageId || ""),
    hint.packageId || "",
    ...(hint.slots || []),
  ];
  for (const src of exactSources) {
    const key = matchBrandMarkExact(src);
    if (key) return { key, letter: firstLetter(key) };
  }

  for (const src of [hint.entry, hint.executor, hint.model]) {
    const key = matchBrandMarkToken(src);
    if (key) return { key, letter: firstLetter(key) };
  }

  const label =
    (hint.displayName || "").trim() ||
    packageParts(hint.packageId || "").slice(-1)[0] ||
    (hint.packageId || "").trim();
  return { key: null, letter: firstLetter(label) };
}

export function resolveMechanismMark(
  raw: string | null | undefined,
): string | null {
  return matchBrandMarkToken(raw);
}
