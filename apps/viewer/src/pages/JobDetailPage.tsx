import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { LoadingState } from "@/components/empty-state";
import { Shell } from "@/components/layout";
import {
  compareValues,
  nextSort,
  SortableHead,
  type SortDir,
} from "@/components/sortable-head";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FileSplitPanel } from "@/components/trial/file-split-panel";
import {
  fetchJob,
  fetchJobOverlayFile,
  fetchJobOverlays,
  type Job,
  type TaskRow,
  type TreeEntry,
} from "@/lib/api";
import { taskHref, taskRunIds } from "@/lib/routes";
import { AxisLabel } from "@/components/axis-label";
import { TruncateTip } from "@/components/hover-tip";
import { ModelLabel } from "@/components/model-label";
import { useDocumentTitle } from "@/lib/document-title";
import { formatError, formatScore } from "@/lib/utils";

type SortKey = "task_id" | "agent_label" | "model_label" | "score" | "status";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  useDocumentTitle(jobId || "Job");
  const [job, setJob] = useState<Job | null>(null);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string | null>("task_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [overlayTree, setOverlayTree] = useState<TreeEntry[]>([]);
  const [overlayPath, setOverlayPath] = useState<string | null>(null);
  const [overlayContent, setOverlayContent] = useState<string | null>(null);
  const [overlayTreeLoading, setOverlayTreeLoading] = useState(false);
  const [overlayFileLoading, setOverlayFileLoading] = useState(false);
  const [overlayNote, setOverlayNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchJob(jobId)
      .then((data) => {
        if (cancelled) return;
        setJob(data.job);
        setTasks(data.tasks || []);
        setError(null);
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
  }, [jobId]);

  const overlayPrefixes = job?.overlays ?? [];

  useEffect(() => {
    if (!overlayPrefixes.length) {
      setOverlayTree([]);
      setOverlayPath(null);
      setOverlayContent(null);
      setOverlayNote(null);
      return;
    }
    let cancelled = false;
    setOverlayTreeLoading(true);
    fetchJobOverlays(jobId)
      .then((data) => {
        if (cancelled) return;
        const items = data.items || [];
        setOverlayTree(items);
        setOverlayPath(items[0]?.path ?? null);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setOverlayTree([]);
          setOverlayNote(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setOverlayTreeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, overlayPrefixes.length]);

  useEffect(() => {
    if (!overlayPath) {
      setOverlayContent(null);
      return;
    }
    let cancelled = false;
    setOverlayFileLoading(true);
    fetchJobOverlayFile(jobId, overlayPath)
      .then((data) => {
        if (cancelled) return;
        setOverlayContent(data.content);
        setOverlayNote(null);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setOverlayContent(null);
          setOverlayNote(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setOverlayFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, overlayPath]);

  const rows = useMemo(() => {
    if (!sortKey || !sortDir) return tasks;
    const key = sortKey as SortKey;
    return [...tasks].sort((a, b) => compareValues(a[key], b[key], sortDir));
  }, [tasks, sortKey, sortDir]);

  function onSort(key: string) {
    const next = nextSort(sortKey, sortDir, key);
    setSortKey(next.dir ? next.key : null);
    setSortDir(next.dir);
  }

  function head(key: string, label: string) {
    return (
      <SortableHead
        label={label}
        active={sortKey === key}
        dir={sortKey === key ? sortDir : null}
        onClick={() => onSort(key)}
      />
    );
  }

  if (!loading && !error && job?.source_kind === "single" && tasks.length === 1) {
    return <Navigate to={taskHref(jobId, tasks[0])} replace />;
  }

  return (
    <Shell>
      <div className="space-y-4">
        <BreadcrumbNav
          items={[
            { label: "Jobs", href: "/" },
            { label: jobId, href: null },
          ]}
        />

        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{jobId}</h1>
          {job && (
            <p className="text-xs text-mute mt-1 flex flex-wrap items-center gap-x-1.5">
              {job.agent_label ? <span>{job.agent_label}</span> : null}
              {job.model_label ? (
                <>
                  {job.agent_label ? <span aria-hidden>/</span> : null}
                  <ModelLabel
                    value={job.model_label}
                    effort={job.reasoning_effort}
                  />
                </>
              ) : null}
              {job.dataset_ref ? (
                <>
                  {job.agent_label || job.model_label ? (
                    <span aria-hidden>/</span>
                  ) : null}
                  <span>{job.dataset_ref}</span>
                </>
              ) : null}
            </p>
          )}
        </div>

        {loading ? (
          <LoadingState label="Loading tasks" />
        ) : (
        <div className="blob-panel overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{head("task_id", "Task")}</TableHead>
                <TableHead>{head("agent_label", "Harness")}</TableHead>
                <TableHead>{head("model_label", "Model")}</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>{head("score", "Avg Reward")}</TableHead>
                <TableHead>Trials</TableHead>
                <TableHead>Errors</TableHead>
                <TableHead>Avg Duration</TableHead>
                <TableHead>{head("status", "Exception")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {error && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-error py-10">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                rows.map((t) => {
                  const errText = formatError(t.error);
                  const isErr =
                    (t.status || "").toUpperCase() === "ERROR" || Boolean(errText);
                  const href = taskHref(jobId, t);
                  const trialCount = t.n ?? taskRunIds(t).length;
                  return (
                    <TableRow
                      key={t.task_id}
                      className="cursor-pointer"
                      tabIndex={0}
                      role="link"
                      onClick={(e) => {
                        const el = e.target as HTMLElement;
                        if (el.closest("button, [role='button']")) return;
                        navigate(href);
                      }}
                      onKeyDown={(e) => {
                        const el = e.target as HTMLElement;
                        if (el.closest("button, [role='button']")) return;
                        if (e.key === "Enter") {
                          navigate(href);
                        }
                      }}
                    >
                      <TableCell className="font-medium max-w-[12rem]">
                        <TruncateTip text={t.task_id} copyable />
                      </TableCell>
                      <TableCell className="max-w-[14rem]">
                        <AxisLabel
                          value={t.agent_label || job?.agent_label}
                          className="block truncate"
                        />
                      </TableCell>
                      <TableCell className="max-w-[18rem]">
                        <ModelLabel
                          value={t.model_label || job?.model_label}
                          effort={t.reasoning_effort || job?.reasoning_effort}
                          className="truncate"
                        />
                      </TableCell>
                      <TableCell className="text-body">
                        {t.dataset || job?.dataset_ref || "-"}
                      </TableCell>
                      <TableCell className="tabular">{formatScore(t.score)}</TableCell>
                      <TableCell className="tabular">{trialCount || 1}</TableCell>
                      <TableCell className="tabular">
                        {isErr || (t.status || "").toUpperCase() === "ERROR" ? 1 : 0}
                      </TableCell>
                      <TableCell className="text-mute">{t.duration || "-"}</TableCell>
                      <TableCell
                        className={
                          isErr || (t.status || "").toUpperCase() === "FAIL"
                            ? "text-error"
                            : "text-mute"
                        }
                      >
                        {errText ||
                          ((t.status || "").toUpperCase() === "ERROR"
                            ? "ERROR"
                            : (t.status || "").toUpperCase() === "FAIL"
                              ? "FAIL"
                              : "-")}
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </div>
        )}

        {overlayPrefixes.length ? (
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Published files</h2>
            <p className="text-xs text-mute">
              Declared <code className="font-mono">overlays:</code> from this
              job binding. Files are read from the opened Dataset root.
            </p>
            <div className="blob-panel overflow-hidden">
              <FileSplitPanel
                tree={overlayTree}
                treeLoading={overlayTreeLoading}
                selectedPath={overlayPath}
                onSelect={setOverlayPath}
                fileContent={overlayContent}
                fileLoading={overlayFileLoading}
                fileNote={overlayNote}
              />
            </div>
          </section>
        ) : null}
      </div>
    </Shell>
  );
}
