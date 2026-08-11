import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

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
import { fetchJobs, type Job } from "@/lib/api";
import { formatDate, formatScore, formatTrials } from "@/lib/utils";

type SortKey =
  | "job_name"
  | "source"
  | "agent_label"
  | "provider_label"
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
  const [agent, setAgent] = useState("all");
  const [provider, setProvider] = useState("all");
  const [model, setModel] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("started");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

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
  }, []);

  const agents = useMemo(
    () =>
      Array.from(new Set(jobs.map((j) => j.agent_label).filter(Boolean) as string[])).sort(),
    [jobs],
  );
  const providers = useMemo(
    () =>
      Array.from(
        new Set(jobs.map((j) => j.provider_label).filter(Boolean) as string[]),
      ).sort(),
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
      if (agent !== "all" && (j.agent_label || "") !== agent) return false;
      if (provider !== "all" && (j.provider_label || "") !== provider) return false;
      if (model !== "all" && (j.model_label || "") !== model) return false;
      if (!query) return true;
      const hay = [
        j.job_name,
        j.source,
        j.agent_label,
        j.model_label,
        j.provider_label,
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
              : a[key];
        const bv =
          key === "result"
            ? (b.mean_score ?? b.result)
            : key === "trials_total"
              ? b.trials_total
              : b[key];
        return compareValues(av, bv, sortDir);
      });
    }
    return rows;
  }, [jobs, q, agent, provider, model, sortKey, sortDir]);

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
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger aria-label="Filter providers">
              <SelectValue placeholder="All providers" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All providers</SelectItem>
              {providers.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
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
                <TableHead>{head("source", "Source")}</TableHead>
                <TableHead>{head("agent_label", "Agents")}</TableHead>
                <TableHead>{head("provider_label", "Providers")}</TableHead>
                <TableHead>{head("model_label", "Models")}</TableHead>
                <TableHead>{head("result", "Result")}</TableHead>
                <TableHead>{head("environment", "Environment")}</TableHead>
                <TableHead>{head("started", "Started")}</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>{head("trials_total", "Trials")}</TableHead>
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
                    {jobs.length === 0 ? (
                      <div className="max-w-lg mx-auto space-y-2 text-sm">
                        <p className="font-medium text-ink">No suite jobs yet</p>
                        <p>
                          Jobs come from{" "}
                          <code className="font-mono text-xs bg-canvas-soft px-1.5 py-0.5 rounded">
                            .bora/suite-runs/
                          </code>{" "}
                          only. A single-task run does{" "}
                          <strong className="font-medium text-body">not</strong>{" "}
                          create a Job.
                        </p>
                        <p>
                          Run a full suite (omit{" "}
                          <code className="font-mono text-xs bg-canvas-soft px-1.5 py-0.5 rounded">
                            --task
                          </code>
                          ), then refresh:
                        </p>
                        <p>
                          <code className="font-mono text-xs bg-canvas-soft px-1.5 py-0.5 rounded">
                            bora run &lt;database&gt;
                          </code>
                        </p>
                      </div>
                    ) : (
                      <span>No jobs match the current filters.</span>
                    )}
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filtered.map((job) => (
                  <TableRow
                    key={job.job_id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/jobs/${encodeURIComponent(job.job_id)}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        navigate(`/jobs/${encodeURIComponent(job.job_id)}`);
                      }
                    }}
                    tabIndex={0}
                    role="link"
                  >
                    <TableCell className="font-medium">{job.job_name}</TableCell>
                    <TableCell className="text-body">{job.source || "-"}</TableCell>
                    <TableCell>{job.agent_label || "-"}</TableCell>
                    <TableCell>{job.provider_label || "-"}</TableCell>
                    <TableCell>{job.model_label || "-"}</TableCell>
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
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </Shell>
  );
}
