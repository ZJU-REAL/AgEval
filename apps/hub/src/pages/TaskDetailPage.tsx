import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { Shell } from "@/components/layout";
import { Markdown } from "@/components/markdown";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  decodeDatasetId,
  decodeFileContent,
  getPackageFile,
  listPackageFiles,
  listPackageVersions,
  listSuites,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";
import { cn, formatScore } from "@/lib/utils";

type Tab = "readme" | "files" | "jobs";

export function TaskDetailPage() {
  const { datasetId: rawId, taskId: rawTask } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const taskId = decodeURIComponent(rawTask || "");
  const [search, setSearch] = useSearchParams();
  // Default tab: README (not Files)
  const tab = (search.get("tab") as Tab) || "readme";

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [readme, setReadme] = useState<string | null>(null);
  const [jobs, setJobs] = useState<
    Array<{
      suite_run_id: string;
      status?: string | null;
      score?: number | null;
      agent_label?: string;
      model_label?: string;
      created_at?: number | string;
    }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const token = getToken();

  const prefix = `tasks/${taskId}`;

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setTreeLoading(true);
      setError(null);
      try {
        const versions = await listPackageVersions(datasetId, token);
        if (!versions.length) {
          throw new RegistryHttpError(404, "not_found", "package not found");
        }
        const latest = [...versions].sort(
          (a, b) => (b.created_at ?? 0) - (a.created_at ?? 0),
        )[0];
        if (cancelled) return;
        setRelease(latest);
        const files = await listPackageFiles(
          datasetId,
          latest.package_digest,
          token,
        );
        if (cancelled) return;
        const nested = buildNestedTree(files.items, prefix);
        setTree(nested);

        // Prefer task.yaml for initial Files selection (when user opens Files)
        const prefer =
          files.items.find((e) => e.path === `${prefix}/task.yaml`) ||
          files.items.find((e) => e.path === `${prefix}/README.md`) ||
          files.items.find(
            (e) => e.type !== "dir" && e.path.startsWith(prefix + "/"),
          );
        if (prefer) setSelectedPath(prefer.path);

        try {
          const r = await getPackageFile(
            datasetId,
            latest.package_digest,
            `${prefix}/README.md`,
            token,
          );
          if (!cancelled) setReadme(decodeFileContent(r));
        } catch {
          if (!cancelled) setReadme(null);
        }

        try {
          const suites: SuiteRow[] = await listSuites(datasetId, token);
          if (cancelled) return;
          const rows: typeof jobs = [];
          for (const s of suites) {
            const refs = s.task_refs || [];
            const hit = refs.find((r) => r.task_id === taskId);
            if (!hit) continue;
            rows.push({
              suite_run_id: s.suite_run_id,
              status: hit.status,
              score: hit.score,
              agent_label: s.agent_label,
              model_label: s.model_label,
              created_at: s.created_at,
            });
          }
          setJobs(rows);
        } catch {
          if (!cancelled) setJobs([]);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setTreeLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [datasetId, taskId, token, prefix]);

  useEffect(() => {
    if (!release || !selectedPath) {
      setFileContent(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    setFileNote(null);
    getPackageFile(datasetId, release.package_digest, selectedPath, token)
      .then((f) => {
        if (cancelled) return;
        setFileContent(decodeFileContent(f));
        if (f.truncated) setFileNote("truncated");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setFileContent(null);
        if (err instanceof RegistryHttpError) {
          setFileNote(`${err.code}: ${err.message}`);
        } else {
          setFileNote(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, release, selectedPath, token]);

  const runCmd = useMemo(() => {
    if (!release) return `bora run ${datasetId} --task ${taskId}`;
    return `bora run registry://${datasetId}@${release.version} --task ${taskId}`;
  }, [datasetId, release, taskId]);

  function setTab(next: Tab) {
    const n = new URLSearchParams(search);
    if (next === "readme") n.delete("tab");
    else n.set("tab", next);
    setSearch(n, { replace: true });
  }

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Datasets", href: "/datasets" },
          {
            label: datasetId,
            href: `/datasets/${encodeURIComponent(datasetId)}`,
          },
          { label: taskId },
        ]}
        className="mb-4"
      />
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
          {taskId}
        </h1>
        <p className="text-sm text-mute mt-1">{datasetId}</p>
      </div>

      <div className="mb-4 max-w-3xl">
        <CommandStrip command={runCmd} />
      </div>

      <div className="flex gap-1 border-b border-hairline mb-4">
        {(
          [
            ["readme", "README"],
            ["files", "Files"],
            ["jobs", "Jobs"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "px-3 py-2 text-sm transition-colors border-b-2 -mb-px",
              tab === id
                ? "border-ink text-ink font-medium"
                : "border-transparent text-body hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {error ? (
        <p className="text-sm text-error font-mono mb-4">{error}</p>
      ) : null}

      {tab === "readme" ? (
        readme ? (
          <Markdown source={readme} />
        ) : (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-mute">
            No <code className="font-mono">tasks/{taskId}/README.md</code> —
            open the Files tab for <code className="font-mono">task.yaml</code>.
          </div>
        )
      ) : null}

      {tab === "files" ? (
        <FileSplitPanel
          tree={tree}
          treeLoading={treeLoading}
          selectedPath={selectedPath}
          onSelect={setSelectedPath}
          fileContent={fileContent}
          fileLoading={fileLoading}
          fileNote={fileNote}
          rootPrefix={prefix}
        />
      ) : null}

      {tab === "jobs" ? (
        jobs.length === 0 ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
            <p className="text-sm text-ink font-medium">No Jobs for this task</p>
            <p className="text-sm text-mute">
              Upload suite results after a suite run. Jobs list is summary-only
              (no full evidence browser here — see discussion #43).
            </p>
            <CommandStrip
              command={`bora results upload-suite <database-root> --suite-run-id <id>`}
            />
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-mute">
              List only — click-through to full Run/Attempt evidence is deferred
              (#43).
            </p>
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Suite run</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Model</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.map((j) => (
                    <TableRow key={j.suite_run_id}>
                      <TableCell className="font-mono text-xs">
                        {j.suite_run_id}
                      </TableCell>
                      <TableCell className="text-sm">{j.status || "-"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatScore(j.score)}
                      </TableCell>
                      <TableCell className="text-sm text-body">
                        {j.agent_label || "-"}
                      </TableCell>
                      <TableCell className="text-sm font-mono text-xs">
                        {j.model_label || "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )
      ) : null}
    </Shell>
  );
}
