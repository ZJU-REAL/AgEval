/** Closed Hub catalog. Keys must match services/registry/brand_marks.json.
 *
 * Product marks: official kit / Lobe static SVG / Simple Icons path + official hex.
 * Generic marks: original geometry in assets/. Never invent a vendor logo.
 */

export type BrandMarkGroup = "product" | "generic";

export type BrandMarkEntry = {
  id: string;
  label: string;
  group: BrandMarkGroup;
  file: string;
};

export const BRAND_MARKS: readonly BrandMarkEntry[] = [
  { id: "anthropic", label: "Anthropic", group: "product", file: "anthropic.svg" },
  { id: "claude", label: "Claude", group: "product", file: "claude.svg" },
  { id: "claude-code", label: "Claude Code", group: "product", file: "claude-code.svg" },
  { id: "codex", label: "Codex", group: "product", file: "codex.svg" },
  { id: "docker", label: "Docker", group: "product", file: "docker.svg" },
  { id: "e2b", label: "E2B", group: "product", file: "e2b.png" },
  { id: "gemini", label: "Gemini", group: "product", file: "gemini.svg" },
  { id: "github", label: "GitHub", group: "product", file: "github.svg" },
  { id: "grok", label: "Grok", group: "product", file: "grok.svg" },
  { id: "openai", label: "OpenAI", group: "product", file: "openai.svg" },
  { id: "opencode", label: "OpenCode", group: "product", file: "opencode.svg" },
  { id: "pi", label: "Pi", group: "product", file: "pi.svg" },
  { id: "grid", label: "Grid", group: "generic", file: "grid.svg" },
  { id: "hex", label: "Hex", group: "generic", file: "hex.svg" },
  { id: "orbit", label: "Orbit", group: "generic", file: "orbit.svg" },
  { id: "pulse", label: "Pulse", group: "generic", file: "pulse.svg" },
  { id: "spark", label: "Spark", group: "generic", file: "spark.svg" },
  { id: "stack", label: "Stack", group: "generic", file: "stack.svg" },
];

export const BRAND_MARK_IDS: ReadonlySet<string> = new Set(
  BRAND_MARKS.map((row) => row.id),
);

export const BRAND_MARK_BY_ID = new Map(BRAND_MARKS.map((row) => [row.id, row]));
