import type { AgentAppearance } from "./api";

export type AppearanceGroup = {
  key: string;
  heading: string | null;
  rows: AgentAppearance[];
};

function push(
  map: Map<string, AgentAppearance[]>,
  key: string,
  row: AgentAppearance,
) {
  const list = map.get(key) ?? [];
  list.push(row);
  map.set(key, list);
}

/** Mechanism cards group by overlay model; custom cards by attached package version. */
export function groupAgentAppearances(
  rows: AgentAppearance[],
  opts: { builtin: boolean; selectedModel?: string },
): AppearanceGroup[] {
  if (opts.builtin) {
    const selected = (opts.selectedModel || "").trim();
    if (selected) {
      return [{ key: selected, heading: null, rows }];
    }
    const map = new Map<string, AgentAppearance[]>();
    for (const row of rows) {
      push(map, (row.model || "").trim(), row);
    }
    const keys = [...map.keys()].sort((a, b) => {
      if (!a && !b) return 0;
      if (!a) return 1;
      if (!b) return -1;
      return a.localeCompare(b);
    });
    return keys.map((key) => ({
      key: key || "_empty_model",
      heading: key || "—",
      rows: map.get(key) ?? [],
    }));
  }

  const map = new Map<string, AgentAppearance[]>();
  for (const row of rows) {
    push(map, (row.agent_version || "").trim(), row);
  }
  const keys = [...map.keys()].sort((a, b) => {
    if (!a && !b) return 0;
    if (!a) return 1;
    if (!b) return -1;
    return b.localeCompare(a);
  });
  return keys.map((key) => ({
    key: key || "_unversioned",
    heading: key ? `v${key}` : null,
    rows: map.get(key) ?? [],
  }));
}
