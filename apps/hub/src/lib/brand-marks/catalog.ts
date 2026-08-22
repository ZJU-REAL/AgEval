/** Closed Hub catalog. Keys must match services/registry/brand_marks.json.
 *
 * Product marks: official kit / Lobe static SVG / Simple Icons path + official hex.
 * tone: color = as-is; ink = black mark on a fixed white plate;
 * paper = white-heavy mark on a fixed black plate. Plates do not follow theme.
 */

export type BrandMarkTone = "color" | "ink" | "paper";

export type BrandMarkEntry = {
  id: string;
  label: string;
  file: string;
  tone: BrandMarkTone;
};

export const BRAND_MARKS: readonly BrandMarkEntry[] = [
  { id: "anthropic", label: "Anthropic", file: "anthropic.svg", tone: "ink" },
  { id: "claude", label: "Claude", file: "claude.svg", tone: "color" },
  { id: "claude-code", label: "Claude Code", file: "claude-code.svg", tone: "color" },
  { id: "codex", label: "Codex", file: "codex.svg", tone: "color" },
  { id: "deepseek", label: "DeepSeek", file: "deepseek.svg", tone: "color" },
  { id: "docker", label: "Docker", file: "docker.svg", tone: "color" },
  { id: "gemini", label: "Gemini", file: "gemini.svg", tone: "color" },
  { id: "github", label: "GitHub", file: "github.svg", tone: "ink" },
  { id: "grok", label: "Grok", file: "grok.svg", tone: "ink" },
  { id: "kimi", label: "Kimi", file: "kimi.svg", tone: "paper" },
  { id: "minimax", label: "MiniMax", file: "minimax.svg", tone: "color" },
  { id: "openai", label: "OpenAI", file: "openai.svg", tone: "ink" },
  { id: "opencode", label: "OpenCode", file: "opencode.svg", tone: "ink" },
  { id: "pi", label: "Pi", file: "pi.svg", tone: "ink" },
  { id: "qwen", label: "Qwen", file: "qwen.svg", tone: "color" },
  { id: "zhipu", label: "GLM", file: "zhipu.svg", tone: "color" },
];

export const BRAND_MARK_IDS: ReadonlySet<string> = new Set(
  BRAND_MARKS.map((row) => row.id),
);

export const BRAND_MARK_BY_ID = new Map(BRAND_MARKS.map((row) => [row.id, row]));
