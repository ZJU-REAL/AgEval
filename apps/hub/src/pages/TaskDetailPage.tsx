import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { Markdown } from "@/components/markdown";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VersionSwitcher } from "@/components/version-switcher";
import {
  decodeDatasetId,
  decodeFileContent,
  getPackageFile,
  hasSharedFiles,
  listPackageFiles,
  listPackageVersions,
  listSuites,
  pickPackageVersion,
  type FileItem,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";
import { AxisLabel } from "@/components/axis-label";
import { HoverTip } from "@/components/hover-tip";
import { cn, formatScore } from "@/lib/utils";

type Tab = "readme" | "files" | "jobs";
type FilesScope = "local" | "shared";

export function TaskDetailPage() {
  const { datasetId: rawId, taskId: rawTask } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const taskId = decodeURIComponent(rawTask || "");
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  // Default tab: README (not Files)
  const tab = (search.get("tab") as Tab) || "readme";
  const requestedVersion = search.get("v");

  const [versions, setVersions] = useState<PackageRelease[]>([]);
  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [filesScope, setFilesScope] = useState<FilesScope>("local");
  const [readme, setReadme] = useState<string | null>(null);
  const [jobs, setJobs] = useState<
    Array<{
      suite_run_id: string;
      status?: string | null;
      score?: number | null;
      agent_label?: string;
      model_label?: string;
      created_at?: number | string;
      run_id?: string | null;
      has_attempt_content?: boolean;
    }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const token = getToken();

  const localPrefix = `tasks/${taskId}`;
  const prefix = filesScope === "shared" ? "shared" : localPrefix;
  const sharedPresent = useMemo(() => hasSharedFiles(fileItems), [fileItems]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setTreeLoading(true);
      setError(null);
      try {
        const listed = await listPackageVersions(datasetId, token);
        if (!listed.length) {
          throw new RegistryHttpError(404, "not_found", "package not found");
        }
        const latest = pickPackageVersion(listed, requestedVersion);
        if (!latest) {
          throw new RegistryHttpError(404, "not_found", "package not found");
        }
        if (cancelled) return;
        setVersions(listed);
        setRelease(latest);
        const files = await listPackageFiles(
          datasetId,
          latest.package_digest,
          token,
        );
        if (cancelled) return;
        setFileItems(files.items);
        const nested = buildNestedTree(files.items, localPrefix);
        setTree(nested);

        // Prefer task.yaml for initial Files selection (when user opens Files)
        const prefer =
          files.items.find((e) => e.path === `${localPrefix}/task.yaml`) ||
          files.items.find((e) => e.path === `${localPrefix}/README.md`) ||
          files.items.find(
            (e) => e.type !== "dir" && e.path.startsWith(localPrefix + "/"),
          );
        if (prefer) setSelectedPath(prefer.path);

        try {
          const r = await getPackageFile(
            datasetId,
            latest.package_digest,
            `${localPrefix}/README.md`,
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
              run_id: hit.run_id ?? null,
              has_attempt_content: Boolean(hit.has_attempt_content),
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
  }, [datasetId, taskId, token, localPrefix, requestedVersion]);

  // Rebuild tree when Local | Shared scope changes (#65).
  useEffect(() => {
    if (!fileItems.length) return;
    const nextPrefix = filesScope === "shared" ? "shared" : localPrefix;
    setTree(buildNestedTree(fileItems, nextPrefix));
    const prefer =
      filesScope === "shared"
        ? fileItems.find((e) => e.path === "shared/README.md") ||
          fileItems.find(
            (e) => e.type !== "dir" && e.path.startsWith("shared/"),
          )
        : fileItems.find((e) => e.path === `${localPrefix}/task.yaml`) ||
          fileItems.find((e) => e.path === `${localPrefix}/README.md`) ||
          fileItems.find(
            (e) => e.type !== "dir" && e.path.startsWith(localPrefix + "/"),
          );
    setSelectedPath(prefer?.path ?? null);
    setFileContent(null);
    setFileNote(null);
  }, [filesScope, fileItems, localPrefix]);

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
        if (f.truncated) {
          const full = f.size ?? 0;
          const shown = (f.content || "").length;
          setFileNote(
            full > 0
              ? `Truncated preview: showing first ~${shown.toLocaleString()} of ${full.toLocaleString()} bytes (Hub preview cap).`
              : "Truncated preview (Hub preview size cap).",
          );
        }
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

  function setVersion(next: string) {
    const n = new URLSearchParams(search);
    n.set("v", next);
    setSearch(n, { replace: true });
  }

  return (
    <>
      <BreadcrumbNav
        items={[
          { label: "Datasets", href: "/datasets" },
          {
            label: datasetId,
            href: `/datasets/${encodeURIComponent(datasetId)}${
              requestedVersion ? `?v=${encodeURIComponent(requestedVersion)}` : ""
            }`,
          },
          { label: taskId },
        ]}
        className="mb-4"
      />
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
            {taskId}
          </h1>
          <p className="text-sm text-mute mt-1">{datasetId}</p>
        </div>
        {versions.length > 0 ? (
          <VersionSwitcher
            versions={versions}
            value={release?.version || versions[0].version}
            onChange={setVersion}
          />
        ) : null}
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
              "px-3 py-2 font-mono text-xs uppercase tracking-wide transition-colors border-b-2 -mb-px",
              tab === id
                ? "border-link text-ink font-semibold"
                : "border-transparent text-mute hover:text-body",
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
          fileContent={
            filesScope === "shared" && !sharedPresent
              ? "This Dataset has no shared/ tree in the published package digest."
              : fileContent
          }
          fileLoading={fileLoading}
          fileNote={
            filesScope === "shared" && !sharedPresent
              ? "no shared/"
              : fileNote
          }
          rootPrefix={prefix}
          headerEnd={
            <div
              className="inline-flex rounded-[6px] border border-hairline p-0.5 bg-canvas shrink-0"
              role="group"
              aria-label="Files scope"
            >
              {(
                [
                  ["local", "Local"],
                  ["shared", "Shared"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setFilesScope(id)}
                  className={cn(
                    "px-2 py-0.5 text-[11px] rounded-[4px] transition-colors",
                    filesScope === id
                      ? "bg-canvas-soft text-ink font-medium shadow-sm"
                      : "text-mute hover:text-ink",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          }
        />
      ) : null}

      {tab === "jobs" ? (
        jobs.length === 0 ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
            <p className="text-sm text-ink font-medium">No Jobs for this task</p>
            <p className="text-sm text-mute">
              Upload suite results after a suite run. Full Attempt evidence is
              optional — add{" "}
              <code className="font-mono">--with-attempts</code> when you want
              Jobs to open a read-only evidence browser.
            </p>
            <CommandStrip
              command={`bora results upload-suite <database-root> --suite-run <id> --with-attempts`}
            />
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-mute">
              Each row is this task&apos;s result inside a suite run. Click a
              row with full Attempt evidence to open the detail view (like local
              viewer). Grey rows are summary-only.
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
                  {jobs.map((j) => {
                    const canOpen =
                      Boolean(j.has_attempt_content) && Boolean(j.run_id);
                    const evidenceHref =
                      canOpen && j.run_id
                        ? `/datasets/${encodeURIComponent(datasetId)}/tasks/${encodeURIComponent(taskId)}/attempts/${encodeURIComponent(j.run_id)}`
                        : null;
                    const rowTip = canOpen
                      ? "Open attempt detail"
                      : j.run_id
                        ? "Summary only — full Attempt not uploaded"
                        : "No run_id for this task";
                    return (
                      <TableRow
                        key={j.suite_run_id}
                        className={cn(
                          canOpen && "cursor-pointer",
                          !canOpen && "opacity-70",
                        )}
                        onClick={() => {
                          if (!evidenceHref) return;
                          navigate(evidenceHref);
                        }}
                        onKeyDown={(e) => {
                          if (!evidenceHref) return;
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            navigate(evidenceHref);
                          }
                        }}
                        tabIndex={canOpen ? 0 : undefined}
                        role={canOpen ? "link" : undefined}
                      >
                        <TableCell className="font-mono text-xs">
                          <HoverTip content={rowTip}>
                          <span className="text-ink">{j.suite_run_id}</span>
                          </HoverTip>
                          {!canOpen ? (
                            <span className="ml-2 text-[11px] text-mute font-sans">
                              summary only
                            </span>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-sm">
                          {j.status || "-"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatScore(j.score)}
                        </TableCell>
                        <TableCell className="text-sm text-body">
                          <AxisLabel value={j.agent_label} />
                        </TableCell>
                        <TableCell className="text-sm font-mono text-xs">
                          <AxisLabel value={j.model_label} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            {jobs.some((j) => !j.has_attempt_content) ? (
              <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-4 space-y-2">
                <p className="text-sm text-body">
                  Some rows have summary only. Upload full Attempt trees to
                  enable the evidence browser:
                </p>
                <CommandStrip
                  command={`bora results upload-suite <database-root> --suite-run <id> --with-attempts`}
                />
                <p className="text-xs text-mute">
                  Or backfill one run:{" "}
                  <code className="font-mono">
                    bora results upload &lt;db&gt; --run &lt;run_id&gt;
                  </code>
                </p>
              </div>
            ) : null}
          </div>
        )
      ) : null}
    </>
  );
}
