import { Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DeleteJobDialog } from "@/components/delete-job-dialog";
import { Shell } from "@/components/layout";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { fetchJobs, type Job } from "@/lib/api";
import { jobDisplayName, jobHref } from "@/lib/routes";
import { AxisLabel } from "@/components/axis-label";
import { HoverTip } from "@/components/hover-tip";
import { formatDate, formatScore, formatTrials } from "@/lib/utils";

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
  const [dbId, setDbId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [source, setSource] = useState("all");
  const [agent, setAgent] = useState("all");
  const [model, setModel] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("started");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [pendingDelete, setPendingDelete] = useState<Job | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchJobs()
      .then((data) => {
        if (cancelled) return;
        setJobs(data.items || []);
        setDbId(data.database_id || "");
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
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(query);
    });
    if (sortKey && sortDir) {
      const key = sortKey as SortKey;
      rows = [...rows].sort((a, b) => {
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
    }
    return rows;
  }, [jobs, q, kind, source, showSourceFilter, agent, model, sortKey, sortDir]);

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
        dbId ? (
          <span className="text-xs text-mute font-mono truncate max-w-[40ch]">{dbId}</span>
        ) : null
      }
    >
      <div className="space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-mute" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search for jobs..."
            className="pl-9 h-10"
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
            <SelectTrigger aria-label="Filter agents">
              <SelectValue placeholder="All agents" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All agents</SelectItem>
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
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex-1" />
          <span className="text-xs text-mute">
            {filtered.length} job{filtered.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="rounded-[8px] border border-hairline overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{head("job_name", "Job Name")}</TableHead>
                <TableHead>{head("agent_label", "Agents")}</TableHead>
                <TableHead>{head("model_label", "Models")}</TableHead>
                <TableHead>{head("result", "Result")}</TableHead>
                <TableHead>{head("environment", "Environment")}</TableHead>
                <TableHead>{head("started", "Started")}</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>{head("trials_total", "Trials")}</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={9} className="text-mute py-10 text-center">
                    Loading jobs...
                  </TableCell>
                </TableRow>
              )}
              {!loading && error && (
                <TableRow>
                  <TableCell colSpan={9} className="text-error py-10 text-center">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading && !error && filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-mute py-10 text-center">
                    No jobs yet. Run{" "}
                    <code className="font-mono text-xs bg-canvas-soft px-1.5 py-0.5 rounded">
                      bora run &lt;database&gt;
                    </code>{" "}
                    or a single-task{" "}
                    <code className="font-mono text-xs bg-canvas-soft px-1.5 py-0.5 rounded">
                      bora run &lt;database&gt; --task &lt;id&gt;
                    </code>{" "}
                    then refresh.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filtered.map((job) => (
                  <TableRow
                    key={job.job_id}
                    className="cursor-pointer"
                    onClick={() => navigate(jobHref(job))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        navigate(jobHref(job));
                      }
                    }}
                    tabIndex={0}
                    role="link"
                  >
                    <TableCell className="font-medium max-w-[16rem]">
                      <HoverTip content={jobDisplayName(job)}>
                        <span className="block truncate">
                          {jobDisplayName(job)}
                        </span>
                      </HoverTip>
                    </TableCell>
                    <TableCell className="max-w-[14rem]">
                      <AxisLabel
                        value={job.agent_label}
                        className="block truncate"
                      />
                    </TableCell>
                    <TableCell className="max-w-[18rem]">
                      <AxisLabel
                        value={job.model_label}
                        className="block truncate font-mono text-xs"
                      />
                    </TableCell>
                    <TableCell className="tabular">
                      {formatScore(job.mean_score ?? job.result)}
                    </TableCell>
                    <TableCell>{job.environment || "local"}</TableCell>
                    <TableCell className="tabular text-body">
                      {formatDate(job.started)}
                    </TableCell>
                    <TableCell className="text-mute">{job.duration || "-"}</TableCell>
                    <TableCell className="tabular">
                      {formatTrials(job.trials_done, job.trials_total)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete job ${jobDisplayName(job)}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setPendingDelete(job);
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </div>
      {pendingDelete ? (
        <DeleteJobDialog
          job={pendingDelete}
          onClose={() => setPendingDelete(null)}
          onDeleted={() => {
            setPendingDelete(null);
            setReloadToken((n) => n + 1);
          }}
        />
      ) : null}
    </Shell>
  );
}
