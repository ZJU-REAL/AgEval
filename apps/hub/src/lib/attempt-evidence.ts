/**
 * Client-side projection of uploaded Attempt archives into viewer trial shapes.
 * Mirrors `bora.viewer.trials` tab / tree / trajectory rules (read-only).
 */

import type {
  Trial,
  TrialActor,
  TrajectoryStep,
  TreeEntry,
} from "@/lib/trial-types";

import {
  FIRST_TAB_ORDER,
  normalizeTabId,
  TAB_ORDER,
  TREE_SCOPES,
  type TabId,
} from "@/components/trial/tabs";

const MAX_TRAJECTORY_STEPS = 2_000;
const MAX_JSONL_LINE = 64_000;

const ACP_ENTRY_SUFFIXES = [
  "claude-code",
  "grok-build",
  "opencode",
  "codex",
  "grok",
  "pi",
] as const;

export function runRootPrefix(runId: string): string {
  return `.bora/runs/${runId}`;
}

/** Map archive path → path relative to run root (or null if outside). */
export function toRelPath(archivePath: string, runId: string): string | null {
  const prefix = `${runRootPrefix(runId)}/`;
  const root = runRootPrefix(runId);
  if (archivePath === root) return "";
  if (archivePath.startsWith(prefix)) return archivePath.slice(prefix.length);
  return null;
}

export function toArchivePath(relPath: string, runId: string): string {
  const clean = relPath.replace(/^\/+/, "");
  return clean ? `${runRootPrefix(runId)}/${clean}` : runRootPrefix(runId);
}

export function fileName(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
}

export function hasAnyUnder(relPaths: string[], dir: string): boolean {
  const d = dir.replace(/\/$/, "");
  return relPaths.some((p) => p === d || p.startsWith(d + "/"));
}

/** Same rules as `bora.viewer.trials.surface._available_tabs`. */
export function availableTabsFromPaths(relFiles: string[]): TabId[] {
  const tabs: string[] = [];
  const hasTraj = relFiles.some(
    (p) =>
      p.startsWith("agent/invocations/") && p.endsWith("/trajectory.jsonl"),
  );
  if (hasTraj) tabs.push("trajectory");
  if (hasAnyUnder(relFiles, "agent")) tabs.push("agent");
  if (
    hasAnyUnder(relFiles, "evaluation") ||
    hasAnyUnder(relFiles, "eval_staging") ||
    relFiles.includes("result.json")
  ) {
    tabs.push("verifier");
  }
  if (
    hasAnyUnder(relFiles, "harness") ||
    hasAnyUnder(relFiles, "artifacts") ||
    hasAnyUnder(relFiles, "agent/artifacts")
  ) {
    tabs.push("artifacts");
  }
  if (relFiles.includes("lock.json")) tabs.push("lock");
  if (
    relFiles.includes("effects.jsonl") ||
    relFiles.includes("cleanup.json") ||
    relFiles.includes("summary.json") ||
    relFiles.includes("agent.json") ||
    relFiles.includes("harness.json")
  ) {
    tabs.push("runtime");
  }
  const normalized = tabs.map(normalizeTabId);
  return TAB_ORDER.filter((t) => normalized.includes(t));
}

export function firstTab(tabs: TabId[]): TabId | null {
  return FIRST_TAB_ORDER.find((t) => tabs.includes(t)) || tabs[0] || null;
}

export function treeEntriesForScope(
  relFiles: Array<{ path: string; size?: number }>,
  scope: string,
  invProfileByDir?: Map<string, string | null>,
): { entries: TreeEntry[]; groups: Array<{ key: string; profile_id?: string | null; label?: string }> | null } {
  const scopeNorm = (scope || "root").toLowerCase();
  const asEntry = (rel: string, size?: number, extra?: Partial<TreeEntry>): TreeEntry => ({
    path: rel,
    name: fileName(rel),
    type: "file",
    size: size ?? null,
    ...extra,
  });

  if (scopeNorm === "lock") {
    const hit = relFiles.find((f) => f.path === "lock.json");
    return {
      entries: hit ? [asEntry(hit.path, hit.size)] : [],
      groups: null,
    };
  }

  if (scopeNorm === "runtime" || scopeNorm === "log") {
    const names = [
      "effects.jsonl",
      "cleanup.json",
      "summary.json",
      "agent.json",
      "harness.json",
    ];
    return {
      entries: names
        .map((n) => relFiles.find((f) => f.path === n))
        .filter((f): f is { path: string; size?: number } => !!f)
        .map((f) => asEntry(f.path, f.size)),
      groups: null,
    };
  }

  if (scopeNorm === "verifier" || scopeNorm === "eval" || scopeNorm === "evaluation") {
    const entries: TreeEntry[] = [];
    for (const f of relFiles) {
      if (
        f.path === "result.json" ||
        f.path.startsWith("evaluation/") ||
        f.path.startsWith("eval_staging/")
      ) {
        entries.push(asEntry(f.path, f.size));
      }
    }
    return { entries, groups: null };
  }

  if (scopeNorm === "artifacts") {
    const entries: TreeEntry[] = [];
    for (const f of relFiles) {
      if (
        f.path.startsWith("artifacts/") ||
        f.path.startsWith("harness/") ||
        f.path.startsWith("agent/artifacts/")
      ) {
        entries.push(asEntry(f.path, f.size));
      }
    }
    return { entries, groups: null };
  }

  if (scopeNorm === "agent") {
    const entries: TreeEntry[] = [];
    const profileKeys = new Set<string>();
    for (const f of relFiles) {
      if (!f.path.startsWith("agent/")) continue;
      let profile_id: string | null = null;
      let invocation: string | null = null;
      const m = f.path.match(/^agent\/invocations\/([^/]+)\//);
      if (m) {
        invocation = m[1];
        profile_id = invProfileByDir?.get(m[1]) ?? null;
        if (profile_id) profileKeys.add(profile_id);
      }
      entries.push(asEntry(f.path, f.size, { profile_id, invocation }));
    }
    const groups =
      profileKeys.size >= 2
        ? [...profileKeys].map((k) => ({
            key: k,
            profile_id: k,
            label: k,
          }))
        : null;
    return { entries, groups };
  }

  // root / unknown
  return {
    entries: relFiles.map((f) => asEntry(f.path, f.size)),
    groups: null,
  };
}

export function scopeForTab(tab: TabId): string | null {
  return TREE_SCOPES[tab] ?? null;
}

function profileEntry(profile: Record<string, unknown>): string | null {
  const opts = profile.options;
  if (opts && typeof opts === "object" && !Array.isArray(opts)) {
    const entry = (opts as Record<string, unknown>).entry;
    if (typeof entry === "string" && entry.trim()) return entry.trim();
  }
  const pid = profile.id;
  if (typeof pid !== "string" || !pid) return null;
  const lower = pid.toLowerCase();
  for (const suf of ACP_ENTRY_SUFFIXES) {
    if (lower === suf || lower.endsWith("-" + suf) || lower.endsWith("_" + suf)) {
      return suf;
    }
  }
  return null;
}

function profileRole(profileId: string, entry: string | null): string {
  if (entry) {
    for (const sep of ["-", "_"] as const) {
      const suffix = sep + entry;
      if (
        profileId.toLowerCase().endsWith(suffix.toLowerCase()) &&
        profileId.length > suffix.length
      ) {
        return profileId.slice(0, -suffix.length);
      }
    }
  }
  return profileId;
}

function dockerLabel(
  result: Record<string, unknown>,
  summary: Record<string, unknown>,
): string | null {
  const runtimeKind = String(result.runtime_kind || summary.runtime_kind || "");
  const assurance = String(result.assurance || summary.assurance || "");
  let l1 = result.l1;
  if (!l1 || typeof l1 !== "object") l1 = summary.l1;
  const isDocker =
    runtimeKind.toLowerCase().includes("docker") ||
    assurance.toLowerCase() === "l1" ||
    (l1 != null && typeof l1 === "object");
  if (!isDocker) return null;
  const parts = ["docker"];
  if (l1 && typeof l1 === "object" && !Array.isArray(l1)) {
    const o = l1 as Record<string, unknown>;
    if (typeof o.platform === "string" && o.platform) parts.push(o.platform);
    const iso = o.isolation;
    if (iso && typeof iso === "object" && !Array.isArray(iso)) {
      const net = (iso as Record<string, unknown>).network;
      if (typeof net === "string" && net) parts.push(net);
    }
    if (typeof o.execution_location === "string" && o.execution_location) {
      if (!parts.includes(o.execution_location)) parts.push(o.execution_location);
    }
  }
  return parts.join(" · ");
}

function formatLatencyMs(
  total: number | undefined,
  nInv: number,
): string | null {
  if (total == null || Number.isNaN(total)) return nInv > 0 ? `— (${nInv})` : null;
  const sec = total / 1000;
  const label =
    sec >= 10 ? `${Math.round(sec)}s` : sec >= 1 ? `${sec.toFixed(1)}s` : `${Math.round(total)}ms`;
  return nInv > 0 ? `${label} (${nInv})` : label;
}

export function buildTrialMeta(opts: {
  runId: string;
  taskId: string;
  relFiles: string[];
  result: Record<string, unknown>;
  summary: Record<string, unknown>;
  lock: Record<string, unknown>;
  invMetas: Array<{ dirname: string; meta: Record<string, unknown> }>;
}): Trial {
  const { runId, taskId, relFiles, result, summary, lock, invMetas } = opts;
  const tabs = availableTabsFromPaths(relFiles);

  let status =
    (typeof result.status === "string" && result.status) ||
    (typeof summary.status === "string" && summary.status) ||
    null;
  if (status) status = status.toUpperCase();

  let score: number | null = null;
  for (const v of [result.score, summary.score]) {
    if (typeof v === "number" && !Number.isNaN(v)) {
      score = v;
      break;
    }
  }

  let error: string | null = null;
  const errRaw = result.error ?? summary.error;
  if (errRaw != null) {
    error =
      typeof errRaw === "string"
        ? errRaw
        : (() => {
            try {
              return JSON.stringify(errRaw);
            } catch {
              return String(errRaw);
            }
          })();
  }

  const profilesRaw = Array.isArray(lock.profiles) ? lock.profiles : [];
  const byId = new Map<string, Record<string, unknown>>();
  for (const p of profilesRaw) {
    if (p && typeof p === "object" && !Array.isArray(p)) {
      const pid = (p as Record<string, unknown>).id;
      if (typeof pid === "string" && pid) byId.set(pid, p as Record<string, unknown>);
    }
  }

  const orderedIds: string[] = [];
  const invModel = new Map<string, string>();
  const invExecutor = new Map<string, string>();
  const latencySum = new Map<string, number>();
  const invokeCount = new Map<string, number>();

  for (const { dirname, meta } of invMetas) {
    const pid = meta.profile_id;
    if (typeof pid !== "string" || !pid) continue;
    if (!orderedIds.includes(pid)) orderedIds.push(pid);
    const mid = meta.model ?? meta.locked_model;
    if (typeof mid === "string" && mid) invModel.set(pid, mid);
    const ek = meta.executor_kind;
    if (typeof ek === "string" && ek) invExecutor.set(pid, ek);
    invokeCount.set(pid, (invokeCount.get(pid) || 0) + 1);
    const lat = meta.latency_ms;
    if (typeof lat === "number" && !Number.isNaN(lat)) {
      latencySum.set(pid, (latencySum.get(pid) || 0) + lat);
    }
    void dirname;
  }
  if (orderedIds.length === 0) {
    for (const pid of byId.keys()) orderedIds.push(pid);
  }

  const actors: TrialActor[] = [];
  const executors: string[] = [];
  for (const pid of orderedIds) {
    const p = byId.get(pid) || { id: pid };
    const entry = profileEntry(p);
    let ex = typeof p.executor === "string" ? p.executor : null;
    if (!ex) ex = invExecutor.get(pid) || null;
    if (ex && !executors.includes(ex)) executors.push(ex);
    const caps = p.capabilities;
    if (
      caps &&
      typeof caps === "object" &&
      !Array.isArray(caps) &&
      (caps as Record<string, unknown>).execution_mode === "acp-stdio" &&
      !executors.includes("acp")
    ) {
      executors.push("acp");
    }
    const model =
      invModel.get(pid) ||
      (typeof p.model === "string" ? p.model : null);
    const agentCol = entry || ex || pid;
    const roleCol = entry ? profileRole(pid, entry) : pid;
    const nInv = invokeCount.get(pid) || 0;
    const latTotal = latencySum.get(pid);
    actors.push({
      role: roleCol,
      agent: agentCol,
      model,
      profile_id: pid,
      invokes: nInv,
      latency_ms_sum: latTotal ?? null,
      time_label: formatLatencyMs(latTotal, nInv),
      usage: null,
      usage_label: null,
    });
  }

  let framework: string | null = null;
  if (
    actors.some((a) =>
      ACP_ENTRY_SUFFIXES.includes(a.agent as (typeof ACP_ENTRY_SUFFIXES)[number]),
    ) ||
    executors.includes("acp")
  ) {
    framework = "acp";
  } else if (executors[0]) {
    framework = executors[0];
  }

  const prov =
    lock.provenance && typeof lock.provenance === "object"
      ? (lock.provenance as Record<string, unknown>)
      : null;
  const upstream =
    prov?.upstream && typeof prov.upstream === "object"
      ? (prov.upstream as Record<string, unknown>)
      : null;

  const startedRaw = summary.started_at ?? summary.started ?? null;
  let started: string | null = null;
  if (typeof startedRaw === "string") started = startedRaw;
  else if (typeof startedRaw === "number") {
    started = new Date(startedRaw * (startedRaw < 1e12 ? 1000 : 1)).toISOString();
  }

  const invCount =
    (typeof result.agent_invocations === "number" && result.agent_invocations) ||
    (typeof summary.agent_invocations === "number" && summary.agent_invocations) ||
    invMetas.length ||
    null;

  return {
    trial_id: runId,
    run_id: runId,
    task_id: taskId,
    status,
    score,
    reward: score,
    error,
    started,
    has_evidence: true,
    available_tabs: tabs,
    agent_invocations: invCount,
    harness_kind:
      (typeof result.harness_kind === "string" && result.harness_kind) ||
      (typeof summary.harness_kind === "string" && summary.harness_kind) ||
      null,
    framework,
    docker: dockerLabel(result, summary),
    actors,
    agent_label: actors.length === 1 ? actors[0].role : null,
    model_label: actors.length === 1 ? actors[0].model ?? null : null,
    executor_kind: executors[0] || null,
    provenance: prov,
    upstream_url:
      typeof upstream?.url === "string" && upstream.url.trim()
        ? upstream.url
        : null,
    upstream_name:
      typeof upstream?.name === "string" && upstream.name.trim()
        ? upstream.name
        : null,
    upstream_ref:
      typeof upstream?.ref === "string" && upstream.ref.trim()
        ? upstream.ref
        : null,
    note: null,
  };
}

/** Parse one trajectory.jsonl body into viewer steps. */
export function parseTrajectoryJsonl(text: string): TrajectoryStep[] {
  const steps: TrajectoryStep[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (steps.length >= MAX_TRAJECTORY_STEPS) break;
    let raw = lines[i].trim();
    if (!raw) continue;
    if (raw.length > MAX_JSONL_LINE) raw = raw.slice(0, MAX_JSONL_LINE);
    let obj: unknown;
    try {
      obj = JSON.parse(raw);
    } catch {
      steps.push({ type: "parse_error", line: i + 1, content: raw.slice(0, 500) });
      continue;
    }
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
      steps.push({ type: "raw", line: i + 1, content: String(obj).slice(0, 500) });
      continue;
    }
    const rec = obj as Record<string, unknown>;
    const role = rec.role;
    const stepType =
      (typeof rec.type === "string" && rec.type) ||
      (role ? "turn" : "event");
    let content = rec.content;
    if (content != null && typeof content !== "string") {
      try {
        content = JSON.stringify(content);
      } catch {
        content = String(content);
      }
    }
    if (typeof content === "string" && content.length > 8_000) {
      content = content.slice(0, 8_000) + "…[truncated]";
    }
    const args = rec.args;
    const rawOutput = rec.raw_output;
    if (stepType === "tool_call" && content == null && args != null) {
      try {
        content = JSON.stringify(args);
      } catch {
        content = String(args);
      }
      if (typeof content === "string" && content.length > 8_000) {
        content = content.slice(0, 8_000) + "…[truncated]";
      }
    }
    if (stepType === "observation" && content == null && rawOutput != null) {
      try {
        content = JSON.stringify(rawOutput);
      } catch {
        content = String(rawOutput);
      }
      if (typeof content === "string" && content.length > 8_000) {
        content = content.slice(0, 8_000) + "…[truncated]";
      }
    }
    steps.push({
      type: stepType,
      role: typeof role === "string" ? role : null,
      content: typeof content === "string" ? content : null,
      turn_index: typeof rec.turn_index === "number" ? rec.turn_index : null,
      source: typeof rec.source === "string" ? rec.source : null,
      stop_reason: typeof rec.stop_reason === "string" ? rec.stop_reason : null,
      ok: typeof rec.ok === "boolean" ? rec.ok : null,
      error: rec.error != null ? String(rec.error) : null,
      line: i + 1,
      usage:
        rec.usage && typeof rec.usage === "object"
          ? (rec.usage as Record<string, unknown>)
          : null,
      metadata:
        rec.metadata && typeof rec.metadata === "object"
          ? (rec.metadata as Record<string, unknown>)
          : null,
      tool_call_id:
        typeof rec.tool_call_id === "string" ? rec.tool_call_id : null,
      title: typeof rec.title === "string" ? rec.title : null,
      function_name:
        typeof rec.function_name === "string" ? rec.function_name : null,
      kind: typeof rec.kind === "string" ? rec.kind : null,
      status: typeof rec.status === "string" ? rec.status : null,
      args: (args as TrajectoryStep["args"]) ?? null,
      raw_output: (rawOutput as TrajectoryStep["raw_output"]) ?? null,
      outcome: typeof rec.outcome === "string" ? rec.outcome : null,
      option_id: typeof rec.option_id === "string" ? rec.option_id : null,
      policy: typeof rec.policy === "string" ? rec.policy : null,
    });
  }
  return steps;
}

export function invDirFromTrajPath(rel: string): string | null {
  const m = rel.match(/^agent\/invocations\/([^/]+)\/trajectory\.jsonl$/);
  return m ? m[1] : null;
}
