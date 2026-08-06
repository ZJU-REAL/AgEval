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
import { cn, formatDate, formatScore } from "@/lib/utils";

type TabId =
  | "trajectory"
  | "agent"
  | "verifier"
  | "artifacts"
  | "lock"
  | "log";

const TAB_LABELS: Record<TabId, string> = {
  trajectory: "Trajectory",
  agent: "Agent",
  verifier: "Verifier",
  artifacts: "Artifacts",
  lock: "Lock",
  log: "Log",
};

const TREE_SCOPES: Partial<Record<TabId, string>> = {
  agent: "agent",
  verifier: "verifier",
  artifacts: "artifacts",
  lock: "lock",
  log: "log",
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
      "log",
    ];
    return order.filter((t) => raw.includes(t));
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
        const tabs = (data.trial.available_tabs || []) as TabId[];
        const first =
          (["trajectory", "agent", "verifier", "lock", "log", "artifacts"] as TabId[]).find(
            (t) => tabs.includes(t),
          ) || null;
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
    fetchTrialTree(jobId, taskId, runId, scope)
      .then((data) => {
        if (cancelled) return;
        const files = (data.entries || []).filter((e) => e.type === "file");
        setTree(files);
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
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-ink font-mono truncate">
              {runId}
            </h1>
            <p className="text-sm text-mute mt-1">
              Attempt evidence · task{" "}
              <span className="text-body font-medium">{taskId}</span>
            </p>
          </div>
          <div className="flex items-center gap-1">
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

function TrajectoryPanel({
  loading,
  steps,
  note,
  result,
}: {
  loading: boolean;
  steps: TrajectoryStep[];
  note: string | null;
  result: Record<string, unknown> | null;
}) {
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
  return (
    <div className="space-y-2">
      {note ? <p className="text-xs text-mute">{note}</p> : null}
      <ol className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
        {steps.map((s, i) => {
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
}: {
  tree: TreeEntry[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-0 rounded-[8px] border border-hairline overflow-hidden min-h-[320px]">
      <aside className="border-b md:border-b-0 md:border-r border-hairline bg-canvas-soft max-h-[50vh] md:max-h-[70vh] overflow-y-auto">
        {treeLoading ? (
          <p className="text-xs text-mute p-3">Loading tree…</p>
        ) : tree.length === 0 ? (
          <p className="text-xs text-mute p-3">No files in this scope.</p>
        ) : (
          <ul className="py-1">
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
      <div className="p-3 max-h-[70vh] overflow-auto">
        {fileLoading ? (
          <p className="text-sm text-mute">Loading file…</p>
        ) : (
          <>
            {fileNote ? <p className="text-xs text-mute mb-2">{fileNote}</p> : null}
            {fileContent != null ? (
              <pre className="m-0 whitespace-pre-wrap break-words font-mono text-[12px] leading-5 text-body">
                {fileContent}
              </pre>
            ) : (
              <p className="text-sm text-mute">Select a file to preview.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
