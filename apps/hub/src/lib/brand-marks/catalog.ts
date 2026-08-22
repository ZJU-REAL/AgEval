/** Closed Hub catalog. Keys must match services/registry/brand_marks.json. */

export type BrandMarkKind = "environment" | "entry" | "vendor" | "protocol";

export type BrandMarkEntry = {
  id: string;
  label: string;
  aliases: string[];
  kind: BrandMarkKind;
};

export const BRAND_MARKS: readonly BrandMarkEntry[] = [
  { id: "acp", label: "ACP", aliases: ["acp"], kind: "protocol" },
  {
    id: "anthropic",
    label: "Anthropic",
    aliases: ["anthropic"],
    kind: "vendor",
  },
  {
    id: "claude",
    label: "Claude",
    aliases: ["claude", "claude-code", "claudecode"],
    kind: "entry",
  },
  {
    id: "codex",
    label: "Codex",
    aliases: ["codex", "openai-codex"],
    kind: "entry",
  },
  { id: "daytona", label: "Daytona", aliases: ["daytona"], kind: "environment" },
  { id: "docker", label: "Docker", aliases: ["docker"], kind: "environment" },
  { id: "e2b", label: "E2B", aliases: ["e2b", "e2b-dev"], kind: "environment" },
  { id: "github", label: "GitHub", aliases: ["github"], kind: "vendor" },
  {
    id: "google",
    label: "Google",
    aliases: ["google", "gemini", "googlegemini", "google-gemini"],
    kind: "vendor",
  },
  { id: "local", label: "Local", aliases: ["local"], kind: "environment" },
  {
    id: "openai",
    label: "OpenAI",
    aliases: ["openai", "chatgpt"],
    kind: "vendor",
  },
  {
    id: "opencode",
    label: "OpenCode",
    aliases: ["opencode"],
    kind: "entry",
  },
  {
    id: "pi",
    label: "Pi",
    aliases: ["pi", "pi-acp", "pi-coding-agent"],
    kind: "entry",
  },
  { id: "ssh", label: "SSH", aliases: ["ssh"], kind: "environment" },
  { id: "xai", label: "xAI", aliases: ["xai", "grok"], kind: "vendor" },
];

export const BRAND_MARK_IDS: ReadonlySet<string> = new Set(
  BRAND_MARKS.map((row) => row.id),
);

const ALIAS_TO_ID = new Map<string, string>();
for (const row of BRAND_MARKS) {
  ALIAS_TO_ID.set(row.id, row.id);
  for (const alias of row.aliases) {
    ALIAS_TO_ID.set(alias, row.id);
  }
}

export function normalizeMarkToken(raw: string): string {
  return raw.trim().toLowerCase().replace(/_/g, "-");
}

/** Exact catalog id or alias. No substring search. */
export function matchBrandMarkExact(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const token = normalizeMarkToken(raw);
  if (!token) return null;
  return ALIAS_TO_ID.get(token) ?? null;
}

/**
 * Exact match, or ``alias-`` / ``alias/`` prefix (model ids like ``claude-sonnet``).
 * Only against this catalog — not a vendor library.
 */
export function matchBrandMarkToken(raw: string | null | undefined): string | null {
  const exact = matchBrandMarkExact(raw);
  if (exact) return exact;
  if (!raw) return null;
  const token = normalizeMarkToken(raw);
  if (!token) return null;
  for (const [alias, id] of ALIAS_TO_ID) {
    if (token.startsWith(`${alias}-`) || token.startsWith(`${alias}/`)) {
      return id;
    }
  }
  return null;
}
