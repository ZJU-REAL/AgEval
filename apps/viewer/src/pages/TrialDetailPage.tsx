import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { Shell } from "@/components/layout";
import { Button } from "@/components/ui/button";
import {
  fetchTrial,
  fetchTrialFile,
  fetchTrialTrajectory,
  fetchTrialTree,
  type TrajectoryStep,
  type TreeEntry,
  type Trial,
} from "@/lib/api";
import { CodeHighlight } from "@/lib/code-highlight";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, formatDate, formatScore } from "@/lib/utils";

type TabId =
  | "trajectory"
  | "agent"
  | "verifier"
  | "artifacts"
  | "lock"
  | "runtime";

const TAB_LABELS: Record<TabId, string> = {
  trajectory: "Trajectory",
  agent: "Agent",
  verifier: "Verifier",
  artifacts: "Artifacts",
  lock: "Lock",
  // effects / cleanup / summary / agent.json / harness.json — not “log files”
  runtime: "Runtime",
};

const TREE_SCOPES: Partial<Record<TabId, string>> = {
  agent: "agent",
  verifier: "verifier",
  artifacts: "artifacts",
  lock: "lock",
  runtime: "runtime",
};

export function TrialDetailPage() {
  const { jobId = "", taskId = "", runId = "" } = useParams();
  const navigate = useNavigate();
  const [trial, setTrial] = useState<Trial | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [runCommand, setRunCommand] = useState("");
  const [prevId, setPrevId] = useState<string | null>(null);
  const [nextId, setNextId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId | null>(null);

  const [steps, setSteps] = useState<TrajectoryStep[]>([]);
  const [trajNote, setTrajNote] = useState<string | null>(null);
  const [trajLoading, setTrajLoading] = useState(false);

  const [tree, setTree] = useState<TreeEntry[]>([]);
  const [treeGroups, setTreeGroups] = useState<
    Array<{ key: string; profile_id?: string | null; label?: string }> | null
  >(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  const availableTabs = useMemo(() => {
    const raw = (trial?.available_tabs || []) as string[];
    const order: TabId[] = [
      "trajectory",
      "agent",
      "verifier",
      "artifacts",
      "lock",
      "runtime",
    ];
    // Accept legacy API tab id "log" as runtime
    const normalized = raw.map((t) => (t === "log" ? "runtime" : t));
    return order.filter((t) => normalized.includes(t));
  }, [trial]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setActiveTab(null);
    setSteps([]);
    setTree([]);
    setSelectedPath(null);
    setFileContent(null);
    fetchTrial(jobId, taskId, runId)
      .then((data) => {
        if (cancelled) return;
        setTrial(data.trial);
        setResult(data.result || null);
        setRunCommand(data.run_command || "");
        setPrevId(data.prev_run_id || null);
        setNextId(data.next_run_id || null);
        setError(null);
        const tabs = (data.trial.available_tabs || []).map((t) =>
          t === "log" ? "runtime" : t,
        ) as TabId[];
        const first =
          (
            [
              "trajectory",
              "agent",
              "verifier",
              "lock",
              "runtime",
              "artifacts",
            ] as TabId[]
          ).find((t) => tabs.includes(t)) || null;
        setActiveTab(first);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, taskId, runId]);

  useEffect(() => {
    if (!activeTab || !jobId || !taskId || !runId) return;
    let cancelled = false;

    if (activeTab === "trajectory") {
      setTrajLoading(true);
      fetchTrialTrajectory(jobId, taskId, runId)
        .then((data) => {
          if (cancelled) return;
          setSteps(data.steps || []);
          setTrajNote(data.note || null);
        })
        .catch((e: Error) => {
          if (!cancelled) setTrajNote(e.message);
        })
        .finally(() => {
          if (!cancelled) setTrajLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }

    const scope = TREE_SCOPES[activeTab];
    if (!scope) return;
    setTreeLoading(true);
    setSelectedPath(null);
    setFileContent(null);
    setFileNote(null);
    setTreeGroups(null);
    fetchTrialTree(jobId, taskId, runId, scope)
      .then((data) => {
        if (cancelled) return;
        const files = (data.entries || []).filter((e) => e.type === "file");
        setTree(files);
        setTreeGroups(data.groups || null);
        // Auto-open a sensible default file
        const preferred =
          files.find((f) => f.name === "lock.json") ||
          files.find((f) => f.name === "result.json") ||
          files.find((f) => f.name.endsWith(".json")) ||
          files[0];
        if (preferred) {
          setSelectedPath(preferred.path);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setFileNote(e.message);
      })
      .finally(() => {
        if (!cancelled) setTreeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, jobId, taskId, runId]);

  useEffect(() => {
    if (!selectedPath || !jobId || !taskId || !runId) return;
    let cancelled = false;
    setFileLoading(true);
    fetchTrialFile(jobId, taskId, runId, selectedPath)
      .then((data) => {
        if (cancelled) return;
        setFileContent(data.content ?? null);
        setFileNote(data.note || (data.truncated ? "truncated preview" : null));
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setFileContent(null);
          setFileNote(e.message);
        }
      })
      .finally(() => {
        if (!cancelled) setFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPath, jobId, taskId, runId]);

  const status = (trial?.status || "").toUpperCase();
  const bad =
    status === "ERROR" || status === "FAIL" || Boolean(trial?.error);

  function goSibling(id: string | null) {
    if (!id) return;
    navigate(
      `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}/trials/${encodeURIComponent(id)}`,
    );
  }

  return (
    <Shell>
      <div className="space-y-5">
        <BreadcrumbNav
          items={[
            { label: "Jobs", href: "/" },
            { label: jobId, href: `/jobs/${encodeURIComponent(jobId)}` },
            {
              label: taskId,
              href: `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}`,
            },
            { label: runId, href: null },
          ]}
        />

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight text-ink font-mono truncate">
              {runId}
            </h1>
            {/* Same mute/body style: task · framework · docker · upstream(if any) */}
            <p className="text-sm text-mute mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <span>
                task{" "}
                <span className="text-body font-medium">{taskId}</span>
              </span>
              {trial?.framework ? (
                <>
                  <span className="text-mute select-none" aria-hidden>
                    ·
                  </span>
                  <span className="text-body font-medium font-mono text-[13px]">
                    {trial.framework}
                  </span>
                </>
              ) : null}
              {trial?.docker ? (
                <>
                  <span className="text-mute select-none" aria-hidden>
                    ·
                  </span>
                  <span className="text-body font-medium font-mono text-[13px]">
                    {trial.docker}
                  </span>
                </>
              ) : null}
              {trial?.upstream_url ? (
                <>
                  <span className="text-mute select-none" aria-hidden>
                    ·
                  </span>
                  <a
                    href={trial.upstream_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-link hover:text-link-deep font-mono text-[13px] truncate max-w-[min(48ch,100%)]"
                    title={trial.upstream_name || trial.upstream_url}
                  >
                    {trial.upstream_url}
                  </a>
                </>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={!prevId}
              onClick={() => goSibling(prevId)}
              aria-label="Previous trial"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={!nextId}
              onClick={() => goSibling(nextId)}
              aria-label="Next trial"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {runCommand ? <CommandStrip command={runCommand} /> : null}

        {loading && <p className="text-sm text-mute">Loading trial…</p>}
        {error && <p className="text-sm text-error">{error}</p>}

        {!loading && !error && trial && (
          <>
            {/* Outcome strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded-[8px] border border-hairline p-4">
              <Outcome label="Status">
                <span className={bad ? "text-error font-medium" : "text-ink font-medium"}>
                  {status || "-"}
                </span>
              </Outcome>
              <Outcome label="Score">
                <span className="tabular">{formatScore(trial.score ?? trial.reward)}</span>
              </Outcome>
              <Outcome label="Started">
                <span className="tabular text-body">{formatDate(trial.started)}</span>
              </Outcome>
              <Outcome label="Invocations">
                <span className="tabular">
                  {trial.agent_invocations != null ? trial.agent_invocations : "-"}
                </span>
              </Outcome>
            </div>
            {trial.note ? (
              <p className="text-xs text-mute">{trial.note}</p>
            ) : null}
            {trial.error ? (
              <p className="text-sm text-error rounded-[8px] bg-error-soft/40 px-3 py-2">
                {String(trial.error)}
              </p>
            ) : null}

            {/* Actors: Role | Agent | Model | Time | Usage — observational ≠ PASS */}
            {trial.actors && trial.actors.length > 0 ? (
              <div className="space-y-1.5">
                <div className="rounded-[8px] border border-hairline overflow-hidden overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead>Role</TableHead>
                        <TableHead>Agent</TableHead>
                        <TableHead>Model</TableHead>
                        <TableHead>Time</TableHead>
                        <TableHead>Usage</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {trial.actors.map((a) => (
                        <TableRow key={a.profile_id || `${a.role}-${a.agent}`}>
                          <TableCell className="font-medium font-mono text-[13px]">
                            {a.role}
                          </TableCell>
                          <TableCell className="font-mono text-[13px] text-body">
                            {a.agent}
                          </TableCell>
                          <TableCell className="font-mono text-[13px] text-mute">
                            {a.model || "-"}
                          </TableCell>
                          <TableCell className="font-mono text-[13px] tabular text-body">
                            {a.time_label || "-"}
                          </TableCell>
                          <TableCell
                            className="font-mono text-[12px] text-mute max-w-[36ch]"
                            title={
                              a.usage_label
                                ? "Observational usage (tokens/cost); not PASS authority. Cache hit = cached_read / input when present. Session-last invoke for cumulative fields."
                                : undefined
                            }
                          >
                            {a.usage_label || "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <p className="text-[11px] text-mute">
                  Time sums inv latency. Usage is last-invoke session snapshot
                  (tokens/cost); trajectory and usage are not PASS.
                </p>
              </div>
            ) : null}

            {/* Tabs */}
            {availableTabs.length === 0 ? (
              <p className="text-sm text-mute">
                No evidence files found for this run under the Database root.
              </p>
            ) : (
              <div className="space-y-3">
                <div
                  role="tablist"
                  aria-label="Evidence tabs"
                  className="flex flex-wrap gap-1 border-b border-hairline pb-0"
                >
                  {availableTabs.map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      role="tab"
                      aria-selected={activeTab === tab}
                      onClick={() => setActiveTab(tab)}
                      className={cn(
                        "px-3 py-2 text-sm transition-colors border-b-2 -mb-px",
                        activeTab === tab
                          ? "border-ink text-ink font-medium"
                          : "border-transparent text-mute hover:text-body",
                      )}
                    >
                      {TAB_LABELS[tab]}
                    </button>
                  ))}
                </div>

                {activeTab === "trajectory" && (
                  <TrajectoryPanel
                    loading={trajLoading}
                    steps={steps}
                    note={trajNote}
                    result={result}
                    actors={trial.actors || []}
                  />
                )}

                {activeTab && activeTab !== "trajectory" && (
                  <FileSplitPanel
                    tree={tree}
                    treeLoading={treeLoading}
                    selectedPath={selectedPath}
                    onSelect={setSelectedPath}
                    fileContent={fileContent}
                    fileLoading={fileLoading}
                    fileNote={fileNote}
                    groupByProfile={activeTab === "agent"}
                    actors={trial.actors || []}
                    apiGroups={treeGroups}
                  />
                )}
              </div>
            )}

            <p className="text-xs text-mute">
              <Link
                to={`/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}`}
                className="text-link hover:text-link-deep"
              >
                ← Back to trials
              </Link>
            </p>
          </>
        )}
      </div>
    </Shell>
  );
}

function Outcome({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="text-xs text-mute mb-0.5">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

type ActorRow = NonNullable<Trial["actors"]>[number];

function actorLabel(a: ActorRow | undefined, profileId: string): string {
  if (!a) return profileId;
  const bits = [a.role || profileId];
  if (a.agent) bits.push(String(a.agent));
  if (a.model) bits.push(String(a.model));
  return bits.join(" · ");
}

function TrajectoryPanel({
  loading,
  steps,
  note,
  result,
  actors,
}: {
  loading: boolean;
  steps: TrajectoryStep[];
  note: string | null;
  result: Record<string, unknown> | null;
  actors: ActorRow[];
}) {
  const groups = useMemo(() => {
    const actorByPid = new Map(
      actors.map((a) => [a.profile_id || `${a.role}-${a.agent}`, a]),
    );
    const order: string[] = [];
    const byProfile = new Map<string, TrajectoryStep[]>();
    for (const s of steps) {
      const key =
        (typeof s.profile_id === "string" && s.profile_id) ||
        "__ungrouped__";
      if (!byProfile.has(key)) {
        byProfile.set(key, []);
        order.push(key);
      }
      byProfile.get(key)!.push(s);
    }
    const multi = order.filter((k) => k !== "__ungrouped__").length >= 2;
    return { order, byProfile, actorByPid, multi };
  }, [steps, actors]);

  if (loading) return <p className="text-sm text-mute">Loading trajectory…</p>;
  if (!steps.length) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-mute">No trajectory.jsonl steps for this run.</p>
        {result ? (
          <pre className="text-[12px] font-mono bg-canvas-soft border border-hairline rounded-[8px] p-3 overflow-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        ) : null}
      </div>
    );
  }

  function renderSteps(list: TrajectoryStep[], showProfileBadge: boolean) {
    return (
      <ol className="space-y-2">
        {list.map((s, i) => {
          const role = (s.role || s.type || "event").toString();
          const isUser = role === "user";
          const isAsst = role === "assistant";
          const isTerminal = s.type === "terminal";
          return (
            <li
              key={`${s.invocation || ""}-${s.line || i}-${i}`}
              className={cn(
                "rounded-[8px] border border-hairline px-3 py-2.5",
                isTerminal && "bg-canvas-soft",
              )}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs text-mute mb-1">
                <span
                  className={cn(
                    "font-medium uppercase tracking-wide",
                    isUser && "text-link",
                    isAsst && "text-ink",
                    isTerminal && "text-mute",
                  )}
                >
                  {role}
                </span>
                {showProfileBadge && s.profile_id ? (
                  <span className="rounded bg-canvas-soft border border-hairline px-1.5 py-0 font-mono text-[11px] text-body">
                    {s.profile_id}
                  </span>
                ) : null}
                {s.turn_index != null ? <span>turn {s.turn_index}</span> : null}
                {s.invocation ? (
                  <span className="font-mono truncate max-w-[24ch]">{s.invocation}</span>
                ) : null}
                {s.stop_reason ? <span>{s.stop_reason}</span> : null}
                {s.ok === false ? <span className="text-error">not ok</span> : null}
              </div>
              {s.content ? (
                <pre className="m-0 whitespace-pre-wrap break-words font-mono text-[13px] leading-5 text-body">
                  {s.content}
                </pre>
              ) : s.error ? (
                <p className="text-sm text-error">{String(s.error)}</p>
              ) : isTerminal ? (
                <p className="text-sm text-mute">terminal</p>
              ) : null}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <div className="space-y-3">
      {note ? <p className="text-xs text-mute">{note}</p> : null}
      <p className="text-[11px] text-mute">
        Trajectory is observational only; independent evaluator owns PASS.
      </p>
      {groups.multi ? (
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {groups.order.map((pid) => {
            const list = groups.byProfile.get(pid) || [];
            const actor =
              pid === "__ungrouped__"
                ? undefined
                : groups.actorByPid.get(pid);
            const title =
              pid === "__ungrouped__"
                ? "ungrouped"
                : actorLabel(actor, pid);
            return (
              <section key={pid} className="space-y-2">
                <h3 className="text-xs font-medium text-ink sticky top-0 bg-canvas/95 backdrop-blur-sm py-1 border-b border-hairline font-mono">
                  {title}
                  <span className="text-mute font-normal ml-2">
                    {list.length} step{list.length === 1 ? "" : "s"}
                  </span>
                </h3>
                {renderSteps(list, false)}
              </section>
            );
          })}
        </div>
      ) : (
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          {renderSteps(steps, false)}
        </div>
      )}
    </div>
  );
}

function FileSplitPanel({
  tree,
  treeLoading,
  selectedPath,
  onSelect,
  fileContent,
  fileLoading,
  fileNote,
  groupByProfile = false,
  actors = [],
  apiGroups = null,
}: {
  tree: TreeEntry[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
  groupByProfile?: boolean;
  actors?: ActorRow[];
  apiGroups?: Array<{
    key: string;
    profile_id?: string | null;
    label?: string;
  }> | null;
}) {
  // Virtual profile folders for multi-role Agent tab (real paths preserved).
  const groupedTree = useMemo(() => {
    if (!groupByProfile || tree.length === 0) return null;
    const profileKeys = new Set(
      tree.map((e) => e.profile_id).filter((p): p is string => !!p),
    );
    if (profileKeys.size < 2) return null;

    const actorByPid = new Map(
      actors.map((a) => [a.profile_id || "", a] as const),
    );
    const order: string[] = [];
    if (apiGroups && apiGroups.length > 0) {
      for (const g of apiGroups) {
        if (g.key && !order.includes(g.key)) order.push(g.key);
      }
    }
    for (const e of tree) {
      const key = e.profile_id || "__ungrouped__";
      if (!order.includes(key)) order.push(key);
    }

    const byKey = new Map<string, TreeEntry[]>();
    for (const e of tree) {
      const key = e.profile_id || "__ungrouped__";
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(e);
    }

    const labels = new Map<string, string>();
    for (const key of order) {
      if (key === "__ungrouped__") {
        labels.set(key, "other");
        continue;
      }
      const actor = actorByPid.get(key);
      labels.set(key, actor ? actorLabel(actor, key) : key);
    }
    return { order, byKey, labels };
  }, [tree, groupByProfile, actors, apiGroups]);

  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-[240px_1fr] gap-0",
        "rounded-[8px] border border-hairline overflow-hidden",
        /* Keep a stable pane even with 1-file trees (e.g. Lock) */
        "min-h-[360px] md:min-h-[420px]",
      )}
    >
      <aside
        className={cn(
          "border-b md:border-b-0 md:border-r border-hairline bg-canvas-soft",
          "min-h-[160px] md:min-h-[420px] max-h-[50vh] md:max-h-[70vh]",
          "overflow-y-auto",
        )}
      >
        {treeLoading ? (
          <p className="text-xs text-mute p-3">Loading tree…</p>
        ) : tree.length === 0 ? (
          <p className="text-xs text-mute p-3">No files in this scope.</p>
        ) : groupedTree ? (
          <div className="py-1 min-h-[140px] md:min-h-[380px]">
            {groupedTree.order.map((key) => (
              <div key={key} className="mb-1">
                <div
                  className="px-3 py-1 text-[11px] font-mono text-mute sticky top-0 bg-canvas-soft border-b border-hairline/60 truncate"
                  title={groupedTree.labels.get(key)}
                >
                  {groupedTree.labels.get(key)}
                </div>
                <ul>
                  {(groupedTree.byKey.get(key) || []).map((e) => (
                    <li key={e.path}>
                      <button
                        type="button"
                        onClick={() => onSelect(e.path)}
                        className={cn(
                          "w-full text-left px-3 py-1.5 text-[12px] font-mono truncate transition-colors",
                          selectedPath === e.path
                            ? "bg-canvas text-ink font-medium"
                            : "text-body hover:bg-canvas/80",
                        )}
                        title={e.path}
                      >
                        {e.invocation ? `${e.invocation}/${e.name}` : e.path}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <ul className="py-1 min-h-[140px] md:min-h-[380px]">
            {tree.map((e) => (
              <li key={e.path}>
                <button
                  type="button"
                  onClick={() => onSelect(e.path)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 text-[12px] font-mono truncate transition-colors",
                    selectedPath === e.path
                      ? "bg-canvas text-ink font-medium"
                      : "text-body hover:bg-row-hover",
                  )}
                  title={e.path}
                >
                  {e.path}
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <div
        className={cn(
          "flex flex-col min-h-[200px] md:min-h-[420px]",
          "max-h-[70vh] overflow-hidden",
        )}
      >
        {selectedPath ? (
          <div className="px-3 py-1.5 border-b border-hairline text-[11px] font-mono text-mute shrink-0 bg-canvas-soft">
            {selectedPath}
          </div>
        ) : null}
        <div className="p-0 flex-1 min-h-0 overflow-auto">
          {fileLoading ? (
            <p className="text-sm text-mute p-3">Loading file…</p>
          ) : (
            <>
              {fileNote ? (
                <p className="text-xs text-mute px-3 pt-2">{fileNote}</p>
              ) : null}
              {fileContent != null ? (
                <pre
                  className={cn(
                    "m-0 p-3 min-h-full overflow-auto",
                    "whitespace-pre-wrap break-words font-mono text-[12px] leading-5",
                    "bg-code-bg text-shell-plain",
                  )}
                >
                  <code className="font-mono">
                    <CodeHighlight path={selectedPath} content={fileContent} />
                  </code>
                </pre>
              ) : (
                <p className="text-sm text-mute p-3">Select a file to preview.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
