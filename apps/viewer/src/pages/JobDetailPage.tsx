import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
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
import { fetchJob, type Job, type TaskRow } from "@/lib/api";
import { taskHref, taskRunIds } from "@/lib/routes";
import { formatError, formatScore } from "@/lib/utils";

type SortKey = "task_id" | "agent_label" | "model_label" | "score" | "status";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string | null>("task_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

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
            <p className="text-sm text-mute mt-1">
              {[job.agent_label, job.model_label, job.source]
                .filter(Boolean)
                .join(" / ")}
            </p>
          )}
        </div>

        <div className="rounded-[8px] border border-hairline overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{head("task_id", "Task")}</TableHead>
                <TableHead>{head("agent_label", "Agent")}</TableHead>
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
              {loading && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-mute py-10">
                    Loading tasks...
                  </TableCell>
                </TableRow>
              )}
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
                      onClick={() => navigate(href)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          navigate(href);
                        }
                      }}
                    >
                      <TableCell className="font-medium max-w-[12rem]">
                        <span className="block truncate" title={t.task_id}>
                          {t.task_id}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[14rem]">
                        <span
                          className="block truncate"
                          title={
                            t.agent_label || job?.agent_label || undefined
                          }
                        >
                          {t.agent_label || job?.agent_label || "-"}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[18rem]">
                        <span
                          className="block truncate font-mono text-xs"
                          title={
                            t.model_label || job?.model_label || undefined
                          }
                        >
                          {t.model_label || job?.model_label || "-"}
                        </span>
                      </TableCell>
                      <TableCell className="text-body">
                        {t.dataset || job?.source || "-"}
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
      </div>
    </Shell>
  );
}
