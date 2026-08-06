import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { Shell } from "@/components/layout";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchJobTask, type Job, type TaskRow, type Trial } from "@/lib/api";
import { cn, formatDate, formatScore } from "@/lib/utils";

export function TaskDetailPage() {
  const { jobId = "", taskId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [task, setTask] = useState<TaskRow | null>(null);
  const [trials, setTrials] = useState<Trial[]>([]);
  const [runCommand, setRunCommand] = useState<string>("");
  const [meta, setMeta] = useState({
    agent: "",
    provider: "",
    model: "",
    dataset: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchJobTask(jobId, taskId)
      .then((data) => {
        if (cancelled) return;
        setJob(data.job);
        setTask(data.task);
        setTrials(data.trials || []);
        setRunCommand(data.run_command || "");
        setMeta({
          agent: data.agent_label || data.job.agent_label || "",
          provider: data.provider_label || data.job.provider_label || "",
          model: data.model_label || data.job.model_label || "",
          dataset: data.dataset || data.job.source || "",
        });
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
  }, [jobId, taskId]);

  return (
    <Shell>
      <div className="space-y-5">
        <BreadcrumbNav
          items={[
            { label: "Jobs", href: "/" },
            { label: jobId, href: `/jobs/${encodeURIComponent(jobId)}` },
            { label: taskId, href: null },
          ]}
        />

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">{taskId}</h1>
            <p className="text-sm text-mute mt-1">
              {[
                meta.agent,
                meta.provider || meta.model
                  ? `(${[meta.provider, meta.model].filter(Boolean).join("/")})`
                  : "",
                meta.dataset,
              ]
                .filter(Boolean)
                .join(" / ")}
            </p>
          </div>
          <p className="text-xs text-mute hidden md:block">
            j k navigate · Enter open · Esc go back
          </p>
        </div>

        {runCommand ? <CommandStrip command={runCommand} /> : null}

        {loading && <p className="text-sm text-mute">Loading trial details...</p>}
        {error && <p className="text-sm text-error">{error}</p>}

        {!loading && !error && (
          <div className="rounded-[8px] border border-hairline overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Trial</TableHead>
                  <TableHead>Reward</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Run id</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trials.map((tr) => {
                  const bad =
                    (tr.status || "").toUpperCase() === "ERROR" ||
                    (tr.status || "").toUpperCase() === "FAIL" ||
                    Boolean(tr.error);
                  const rid = tr.run_id || tr.trial_id || task?.run_id || "";
                  const openable = Boolean(rid);
                  return (
                    <TableRow
                      key={tr.trial_id || rid}
                      className={cn(openable && "cursor-pointer")}
                      onClick={() => {
                        if (!openable) return;
                        navigate(
                          `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}/trials/${encodeURIComponent(rid)}`,
                        );
                      }}
                      onKeyDown={(e) => {
                        if (!openable) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(
                            `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}/trials/${encodeURIComponent(rid)}`,
                          );
                        }
                      }}
                      tabIndex={openable ? 0 : undefined}
                      role={openable ? "link" : undefined}
                    >
                      <TableCell className="font-medium font-mono text-[13px]">
                        {tr.trial_id}
                        {tr.has_evidence ? (
                          <span className="ml-2 text-[11px] text-mute font-sans">
                            evidence
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell
                        className={
                          bad ? "text-error tabular" : "tabular"
                        }
                      >
                        {tr.error ||
                          ((tr.status || "").toUpperCase() === "ERROR"
                            ? "RuntimeError"
                            : (tr.status || "").toUpperCase() === "FAIL"
                              ? formatScore(tr.reward ?? tr.score)
                              : formatScore(tr.reward ?? tr.score))}
                      </TableCell>
                      <TableCell className="text-mute">
                        {tr.duration || "-"}
                      </TableCell>
                      <TableCell className="tabular text-body">
                        {formatDate(tr.started || job?.started)}
                      </TableCell>
                      <TableCell className="font-mono text-[12px] text-mute">
                        {tr.run_id || task?.run_id || "-"}
                      </TableCell>
                      <TableCell
                        className={bad ? "text-error" : "text-body"}
                      >
                        {tr.status || "-"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </Shell>
  );
}
