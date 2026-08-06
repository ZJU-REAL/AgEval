import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

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
import { formatScore } from "@/lib/utils";

type SortKey = "task_id" | "agent_label" | "provider_label" | "model_label" | "score" | "status";

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
              {[job.agent_label, job.provider_label && job.model_label
                ? `(${job.provider_label}/${job.model_label})`
                : job.model_label,
              job.source]
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
                <TableHead>{head("provider_label", "Provider")}</TableHead>
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
                  <TableCell colSpan={10} className="text-center text-mute py-10">
                    Loading tasks...
                  </TableCell>
                </TableRow>
              )}
              {error && (
                <TableRow>
                  <TableCell colSpan={10} className="text-center text-error py-10">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                rows.map((t) => {
                  const isErr =
                    (t.status || "").toUpperCase() === "ERROR" || Boolean(t.error);
                  return (
                    <TableRow
                      key={t.task_id}
                      className="cursor-pointer"
                      tabIndex={0}
                      role="link"
                      onClick={() =>
                        navigate(
                          `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(t.task_id)}`,
                        )
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          navigate(
                            `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(t.task_id)}`,
                          );
                        }
                      }}
                    >
                      <TableCell className="font-medium">{t.task_id}</TableCell>
                      <TableCell>{t.agent_label || job?.agent_label || "-"}</TableCell>
                      <TableCell>
                        {t.provider_label || job?.provider_label || "-"}
                      </TableCell>
                      <TableCell>{t.model_label || job?.model_label || "-"}</TableCell>
                      <TableCell className="text-body">
                        {t.dataset || job?.source || "-"}
                      </TableCell>
                      <TableCell className="tabular">{formatScore(t.score)}</TableCell>
                      <TableCell className="tabular">1</TableCell>
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
                        {t.error ||
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
