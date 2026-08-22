import { ListChecks, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DeleteJobDialog } from "@/components/delete-job-dialog";
import { JobCheck } from "@/components/job-check";
import { JobNoteDialog } from "@/components/job-note-dialog";
import { JobRowActions } from "@/components/job-row-actions";
import { Shell } from "@/components/layout";
import { PageHead } from "@/components/page-head";
import {
  compareValues,
  nextSort,
  SortableHead,
  type SortDir,
} from "@/components/sortable-head";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchJobs, type Job } from "@/lib/api";
import {
  emptyJobPref,
  loadJobPrefs,
  saveJobPrefs,
  type JobPref,
} from "@/lib/job-prefs";
import { jobDisplayName, jobHref } from "@/lib/routes";
import { AxisLabel } from "@/components/axis-label";
import { HoverTip } from "@/components/hover-tip";
import { ModelLabel } from "@/components/model-label";
import { formatDate, formatModelLabel, formatScore, formatTrials } from "@/lib/utils";

type SortKey =
  | "job_name"
  | "agent_label"
  | "model_label"
  | "result"
  | "environment"
  | "started"
  | "trials_total";

export function JobsPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [source, setSource] = useState("all");
  const [agent, setAgent] = useState("all");
  const [model, setModel] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("started");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [pendingDelete, setPendingDelete] = useState<Job[] | null>(null);
  const [pendingNote, setPendingNote] = useState<Job | null>(null);
  const [prefs, setPrefs] = useState<Record<string, JobPref>>({});
  const [selected, setSelected] = useState<Record<string, true>>({});
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchJobs()
      .then((data) => {
        if (cancelled) return;
        setJobs(data.items || []);
        setDatasetId(data.dataset_id || "");
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
  }, [reloadToken]);

  useEffect(() => {
    setPrefs(loadJobPrefs(datasetId));
  }, [datasetId]);

  const writePrefs = useCallback(
    (next: Record<string, JobPref>) => {
      setPrefs(next);
      saveJobPrefs(datasetId, next);
    },
    [datasetId],
  );

  function prefFor(jobId: string): JobPref {
    return prefs[jobId] || emptyJobPref();
  }

  function patchPref(jobId: string, patch: Partial<JobPref>) {
    const merged: JobPref = { ...prefFor(jobId), ...patch };
    const next = { ...prefs };
    if (!merged.pinned && !merged.note.trim()) {
      delete next[jobId];
    } else {
      next[jobId] = merged;
    }
    writePrefs(next);
  }

  const kinds = useMemo(
    () =>
      Array.from(
        new Set(
          jobs.map((j) => (j.source_kind === "single" ? "single" : "suite")),
        ),
      ).sort(),
    [jobs],
  );
  const sources = useMemo(
    () =>
      Array.from(
        new Set(
          jobs
            .filter((j) => j.source_kind === "single")
            .map((j) => j.task_id || "")
            .filter(Boolean),
        ),
      ).sort(),
    [jobs],
  );
  const showSourceFilter = kind !== "suite" && sources.length > 0;
  const agents = useMemo(
    () =>
      Array.from(new Set(jobs.map((j) => j.agent_label).filter(Boolean) as string[])).sort(),
    [jobs],
  );
  const models = useMemo(
    () =>
      Array.from(new Set(jobs.map((j) => j.model_label).filter(Boolean) as string[])).sort(),
    [jobs],
  );

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    let rows = jobs.filter((j) => {
      const rowKind = j.source_kind === "single" ? "single" : "suite";
      if (kind !== "all" && rowKind !== kind) return false;
      if (showSourceFilter && source !== "all" && (j.task_id || "") !== source) {
        return false;
      }
      if (agent !== "all" && (j.agent_label || "") !== agent) return false;
      if (model !== "all" && (j.model_label || "") !== model) return false;
      if (!query) return true;
      const hay = [
        jobDisplayName(j),
        j.job_name,
        j.source,
        j.source_kind,
        j.job_id,
        j.task_id,
        j.agent_label,
        j.model_label,
        j.environment,
        prefs[j.job_id]?.note,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(query);
    });
    rows = [...rows].sort((a, b) => {
      const pin = Number(Boolean(prefs[b.job_id]?.pinned)) - Number(Boolean(prefs[a.job_id]?.pinned));
      if (pin !== 0) return pin;
      if (!sortKey || !sortDir) return 0;
      const key = sortKey as SortKey;
      const av =
        key === "result"
          ? (a.mean_score ?? a.result)
          : key === "trials_total"
            ? a.trials_total
            : key === "job_name"
              ? jobDisplayName(a)
              : a[key];
      const bv =
        key === "result"
          ? (b.mean_score ?? b.result)
          : key === "trials_total"
            ? b.trials_total
            : key === "job_name"
              ? jobDisplayName(b)
              : b[key];
      return compareValues(av, bv, sortDir);
    });
    return rows;
  }, [jobs, q, kind, source, showSourceFilter, agent, model, sortKey, sortDir, prefs]);

  const selectedVisible = filtered.filter((j) => selected[j.job_id]);
  const selectedCount = selectedVisible.length;
  const allVisibleSelected =
    filtered.length > 0 && selectedVisible.length === filtered.length;
  const someVisibleSelected = selectedVisible.length > 0 && !allVisibleSelected;

  function toggleOne(jobId: string, next: boolean) {
    setSelected((prev) => {
      const copy = { ...prev };
      if (next) copy[jobId] = true;
      else delete copy[jobId];
      return copy;
    });
  }

  function toggleAllVisible(next: boolean) {
    setSelected((prev) => {
      const copy = { ...prev };
      for (const job of filtered) {
        if (next) copy[job.job_id] = true;
        else delete copy[job.job_id];
      }
      return copy;
    });
  }

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
    <Shell
      meta={
        datasetId ? (
          <span className="text-xs text-mute font-mono truncate max-w-[40ch]">{datasetId}</span>
        ) : null
      }
    >
      <div className="space-y-4">
        <PageHead title="Jobs" />
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-mute" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search for jobs..."
            className="pl-9 h-10 focus-visible:border-hairline"
            aria-label="Search jobs"
          />
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <Select
            value={kind}
            onValueChange={(next) => {
              setKind(next);
              if (next === "suite") setSource("all");
            }}
          >
            <SelectTrigger aria-label="Filter kind">
              <SelectValue placeholder="All kinds" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All kinds</SelectItem>
              {kinds.map((k) => (
                <SelectItem key={k} value={k}>
                  {k === "single" ? "single" : "suite"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {showSourceFilter ? (
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger aria-label="Filter source">
                <SelectValue placeholder="All sources" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All sources</SelectItem>
                {sources.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <Select value={agent} onValueChange={setAgent}>
            <SelectTrigger aria-label="Filter harnesses">
              <SelectValue placeholder="All harnesses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All harnesses</SelectItem>
              {agents.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger aria-label="Filter models">
              <SelectValue placeholder="All models" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All models</SelectItem>
              {models.map((m) => (
                <SelectItem key={m} value={m}>
                  {formatModelLabel(m).text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex-1" />
          {selectedCount > 0 ? (
            <Button
              type="button"
              variant="dangerOutline"
              size="sm"
              onClick={() => {
                const rows = filtered.filter((j) => selected[j.job_id]);
                if (rows.length) setPendingDelete(rows);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete {selectedCount}
            </Button>
          ) : (
            <span className="text-xs text-mute">
              {filtered.length} job{filtered.length === 1 ? "" : "s"}
            </span>
          )}
        </div>

        {!loading && !error && jobs.length === 0 ? (
          <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm">
            <div className="mb-4 flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-[12px] border border-hairline bg-canvas text-mute">
                <ListChecks className="h-8 w-8" strokeWidth={1.5} aria-hidden />
              </div>
            </div>
            <p className="font-medium text-ink">No jobs yet</p>
            <p className="mt-1 text-mute">
              Run{" "}
              <code className="font-mono text-xs bg-canvas px-1.5 py-0.5 rounded-[6px] text-body">
                ageval run &lt;dataset&gt;
              </code>{" "}
              or a single-task{" "}
              <code className="font-mono text-xs bg-canvas px-1.5 py-0.5 rounded-[6px] text-body">
                ageval run &lt;dataset&gt; --task &lt;id&gt;
              </code>
              , then refresh.
            </p>
          </div>
        ) : (
          <div className="rounded-[8px] border border-hairline overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-8 pr-0">
                  <JobCheck
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected}
                    label="Select all jobs"
                    onChange={toggleAllVisible}
                  />
                </TableHead>
                <TableHead>{head("job_name", "Job Name")}</TableHead>
                <TableHead>{head("agent_label", "Harness")}</TableHead>
                <TableHead>{head("model_label", "Models")}</TableHead>
                <TableHead>{head("result", "Result")}</TableHead>
                <TableHead>{head("environment", "Environment")}</TableHead>
                <TableHead>{head("started", "Started")}</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>{head("trials_total", "Trials")}</TableHead>
                <TableHead className="w-7 pl-0 pr-2">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={10} className="text-mute py-10 text-center">
                    Loading jobs...
                  </TableCell>
                </TableRow>
              )}
              {!loading && error && (
                <TableRow>
                  <TableCell colSpan={10} className="text-error py-10 text-center">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading && !error && filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className="text-mute py-10 text-center">
                    No matching jobs.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filtered.map((job) => (
                  <TableRow
                    key={job.job_id}
                    className="group cursor-pointer"
                    onClick={(e) => {
                      const el = e.target as HTMLElement;
                      if (el.closest("input, button, [role='menu'], [role='menuitem']")) {
                        return;
                      }
                      navigate(jobHref(job));
                    }}
                    onKeyDown={(e) => {
                      const el = e.target as HTMLElement;
                      if (el.closest("input, button")) return;
                      if (e.key === "Enter") {
                        navigate(jobHref(job));
                      }
                    }}
                    tabIndex={0}
                    role="link"
                  >
                    <TableCell className="w-8 pr-0">
                      <JobCheck
                        checked={Boolean(selected[job.job_id])}
                        label={`Select ${jobDisplayName(job)}`}
                        onChange={(next) => toggleOne(job.job_id, next)}
                      />
                    </TableCell>
                    <TableCell className="font-medium max-w-[16rem]">
                      <HoverTip content={jobDisplayName(job)}>
                        <span className="block truncate">{jobDisplayName(job)}</span>
                      </HoverTip>
                    </TableCell>
                    <TableCell className="max-w-[14rem]">
                      <AxisLabel
                        value={job.agent_label}
                        className="block truncate"
                      />
                    </TableCell>
                    <TableCell className="max-w-[18rem]">
                      <ModelLabel
                        value={job.model_label}
                        effort={job.reasoning_effort}
                        className="truncate font-mono text-xs"
                      />
                    </TableCell>
                    <TableCell className="tabular">
                      {formatScore(job.mean_score ?? job.result)}
                    </TableCell>
                    <TableCell>{job.environment || "-"}</TableCell>
                    <TableCell className="tabular text-body">
                      {formatDate(job.started)}
                    </TableCell>
                    <TableCell className="text-mute">{job.duration || "-"}</TableCell>
                    <TableCell className="tabular">
                      {formatTrials(job.trials_done, job.trials_total)}
                    </TableCell>
                    <TableCell className="w-7 pl-0 pr-2 text-right">
                      <JobRowActions
                        job={job}
                        pref={prefFor(job.job_id)}
                        onPin={() =>
                          patchPref(job.job_id, {
                            pinned: !prefFor(job.job_id).pinned,
                          })
                        }
                        onNote={() => setPendingNote(job)}
                        onDelete={() => setPendingDelete([job])}
                      />
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
          </div>
        )}
      </div>
      {pendingNote ? (
        <JobNoteDialog
          job={pendingNote}
          initialNote={prefFor(pendingNote.job_id).note}
          onClose={() => setPendingNote(null)}
          onSave={(note) => {
            patchPref(pendingNote.job_id, { note });
            setPendingNote(null);
          }}
        />
      ) : null}
      {pendingDelete ? (
        <DeleteJobDialog
          jobs={pendingDelete}
          onClose={() => setPendingDelete(null)}
          onDeleted={(jobIds) => {
            const nextPrefs = { ...prefs };
            const nextSelected = { ...selected };
            for (const id of jobIds) {
              delete nextPrefs[id];
              delete nextSelected[id];
            }
            writePrefs(nextPrefs);
            setSelected(nextSelected);
            setPendingDelete(null);
            setReloadToken((n) => n + 1);
          }}
        />
      ) : null}
    </Shell>
  );
}
