import { BRAND_MARK_IDS, matchBrandMarkExact } from "@/lib/brand-marks/catalog";

export type EntityMarkHint = {
  iconKey?: string | null;
  packageId?: string | null;
  displayName?: string | null;
  slots?: string[];
  entry?: string | null;
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

  const leaf = packageParts(hint.packageId || "").slice(-1)[0] || "";
  for (const src of [leaf, ...(hint.slots || []), hint.entry]) {
    const key = matchBrandMarkExact(src);
    if (key) return { key, letter: firstLetter(key) };
  }

  const label =
    (hint.displayName || "").trim() || leaf || (hint.packageId || "").trim();
  return { key: null, letter: firstLetter(label) };
}

export function resolveMechanismMark(
  raw: string | null | undefined,
): string | null {
  return matchBrandMarkExact(raw);
}
