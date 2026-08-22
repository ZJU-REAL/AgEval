import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { CatalogHead } from "@/components/page-head";
import { UnderlineTabs } from "@/components/underline-tabs";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { OverlayFilePanel } from "@/components/overlay-file-panel";
import { Markdown } from "@/components/markdown";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PillTabs } from "@/components/ui/pill-tabs";
import { VersionSwitcher } from "@/components/version-switcher";
import {
  decodeDatasetId,
  decodeFileContent,
  environmentFromOverlay,
  getPackageFile,
  hasSharedFiles,
  listAttempts,
  listPackageFiles,
  listPackageVersions,
  listSuites,
  pickPackageVersion,
  type FileItem,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, overlayPathsFromProfilesYaml, type TreeNode } from "@/lib/file-tree";
import { AxisLabel } from "@/components/axis-label";
import { HoverTip } from "@/components/hover-tip";
import { ModelLabel } from "@/components/model-label";
import {
  cn,
  displayLabelsFromOverlay,
  formatDate,
  formatScore,
  reasoningEffortFromOverlay,
} from "@/lib/utils";

type Tab = "readme" | "files" | "jobs";
type FilesScope = "local" | "shared" | "overlays";

function FilesScopeSwitch({
  filesScope,
  onChange,
  localPresent,
  sharedPresent,
  overlaysPresent,
}: {
  filesScope: FilesScope;
  onChange: (next: FilesScope) => void;
  localPresent: boolean;
  sharedPresent: boolean;
  overlaysPresent: boolean;
}) {
  const items = [
    ...(localPresent ? ([{ id: "local" as const, label: "Local" }] as const) : []),
    ...(sharedPresent
      ? ([{ id: "shared" as const, label: "Shared" }] as const)
      : []),
    ...(overlaysPresent
      ? ([{ id: "overlays" as const, label: "Overlays" }] as const)
      : []),
  ];
  if (items.length < 2) return null;
  return (
    <PillTabs
      items={items}
      value={filesScope}
      onChange={onChange}
      ariaLabel="Files scope"
    />
  );
}

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
  const [overlayPrefixes, setOverlayPrefixes] = useState<string[]>([]);
  const [readme, setReadme] = useState<string | null>(null);
  const [jobs, setJobs] = useState<
    Array<{
      job_id: string;
      job_kind: "suite" | "attempt";
      status?: string | null;
      score?: number | null;
      agent_label?: string;
      model_label?: string;
      reasoning_effort?: string;
      environment?: string | null;
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
  const localPresent = useMemo(
    () =>
      fileItems.some(
        (item) =>
          item.path === localPrefix || item.path.startsWith(`${localPrefix}/`),
      ),
    [fileItems, localPrefix],
  );
  const overlaysPresent = overlayPrefixes.length > 0;

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
        const profilePaths = files.items
          .filter(
            (item) =>
              item.type !== "dir" &&
              item.path.endsWith(".yaml") &&
              !item.path.startsWith("tasks/") &&
              /(^|\/)profiles(\.|$)/.test(item.path.split("/").pop() || ""),
          )
          .map((item) => item.path);
        try {
          const docs = await Promise.all(
            profilePaths.map((path) =>
              getPackageFile(datasetId, latest.package_digest, path, token)
                .then((file) => decodeFileContent(file))
                .catch(() => ""),
            ),
          );
          if (!cancelled) {
            const seen = new Set<string>();
            const prefixes: string[] = [];
            for (const doc of docs) {
              for (const path of overlayPathsFromProfilesYaml(doc)) {
                if (seen.has(path)) continue;
                seen.add(path);
                prefixes.push(path);
              }
            }
            setOverlayPrefixes(prefixes);
          }
        } catch {
          if (!cancelled) setOverlayPrefixes([]);
        }

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
          const [suites, attempts] = await Promise.all([
            listSuites(datasetId, token),
            listAttempts(datasetId, token, { taskId, standalone: true }),
          ]);
          if (cancelled) return;
          const rows: typeof jobs = [];
          for (const s of suites) {
            const refs = s.task_refs || [];
            const hit = refs.find((r) => r.task_id === taskId);
            if (!hit) continue;
            const derived = displayLabelsFromOverlay(s.job_overlay);
            rows.push({
              job_id: s.suite_run_id,
              job_kind: "suite",
              status: hit.status,
              score: hit.score,
              agent_label: derived.agent || s.agent_label,
              model_label: derived.model || s.model_label,
              reasoning_effort: reasoningEffortFromOverlay(s.job_overlay),
              environment: environmentFromOverlay(s.job_overlay),
              created_at: s.created_at,
              run_id: hit.run_id ?? null,
              has_attempt_content: Boolean(hit.has_attempt_content),
            });
          }
          for (const a of attempts) {
            rows.push({
              job_id: a.run_id,
              job_kind: "attempt",
              status: a.status,
              score: a.score ?? null,
              agent_label: a.agent_label,
              model_label: a.model_label,
              environment: a.environment || null,
              created_at: a.created_at,
              run_id: a.run_id,
              has_attempt_content: true,
            });
          }
          rows.sort((left, right) => {
            const lt = Date.parse(String(left.created_at ?? "")) || Number(left.created_at) || 0;
            const rt = Date.parse(String(right.created_at ?? "")) || Number(right.created_at) || 0;
            return rt - lt;
          });
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

  // Rebuild tree when Local | Shared | Overlays scope changes.
  useEffect(() => {
    if (!fileItems.length) return;
    if (filesScope === "overlays") {
      setFileContent(null);
      setFileNote(null);
      return;
    }
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
    const available: FilesScope[] = [];
    if (localPresent) available.push("local");
    if (sharedPresent) available.push("shared");
    if (overlaysPresent) available.push("overlays");
    if (!available.length) {
      if (filesScope !== "local") setFilesScope("local");
      return;
    }
    if (!available.includes(filesScope)) setFilesScope(available[0]);
  }, [filesScope, localPresent, overlaysPresent, sharedPresent]);

  useEffect(() => {
    if (!release || !selectedPath || filesScope === "overlays") {
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
  }, [datasetId, filesScope, release, selectedPath, token]);

  const runCmd = useMemo(() => {
    if (!release) return `ageval run ${datasetId} --task ${taskId}`;
    return `ageval run registry://${datasetId}@${release.version} --task ${taskId}`;
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

  const filesScopeSwitch =
    [localPresent, sharedPresent, overlaysPresent].filter(Boolean).length >= 2 ? (
      <FilesScopeSwitch
        filesScope={filesScope}
        onChange={setFilesScope}
        localPresent={localPresent}
        sharedPresent={sharedPresent}
        overlaysPresent={overlaysPresent}
      />
    ) : undefined;

  return (
    <>
      <CatalogHead
        title="Your datasets"
        crumbs={[
          { label: "Your datasets", href: "/datasets" },
          {
            label: datasetId,
            href: `/datasets/${encodeURIComponent(datasetId)}${
              requestedVersion ? `?v=${encodeURIComponent(requestedVersion)}` : ""
            }`,
          },
          { label: taskId },
        ]}
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

      <UnderlineTabs
        className="mb-4"
        ariaLabel="Task sections"
        value={tab}
        onChange={setTab}
        items={[
          { id: "readme", label: "README" },
          { id: "files", label: "Files" },
          { id: "jobs", label: "Jobs" },
        ]}
      />

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
        filesScope === "overlays" && release && overlaysPresent ? (
          <OverlayFilePanel
            datasetId={datasetId}
            packageDigest={release.package_digest}
            prefixes={overlayPrefixes}
            headerEnd={filesScopeSwitch}
          />
        ) : (
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
          headerEnd={filesScopeSwitch}
        />
        )
      ) : null}

      {tab === "jobs" ? (
        jobs.length === 0 ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
            <p className="text-sm text-ink font-medium">No Jobs for this task</p>
            <p className="text-sm text-mute">
              Upload a standalone Attempt after{" "}
              <code className="font-mono">ageval run --task</code>, or a suite
              after a full dataset run. Add{" "}
              <code className="font-mono">--with-attempts</code> on suite upload
              when you want the row to open evidence.
            </p>
            <CommandStrip
              command={`ageval results upload <dataset-root> --run <attempt-id> --public`}
            />
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-mute">
              Each row is a standalone Attempt or this task inside a suite run.
              Click a row with full evidence to open the detail view. Grey rows
              are summary-only.
            </p>
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Job</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead>Harness</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Environment</TableHead>
                    <TableHead>Time</TableHead>
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
                        key={`${j.job_kind}:${j.job_id}`}
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
                          <span className="text-ink">{j.job_id}</span>
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
                          <ModelLabel
                            value={j.model_label}
                            effort={j.reasoning_effort}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {j.environment || "-"}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-mute tabular">
                          {j.created_at != null && j.created_at !== ""
                            ? formatDate(j.created_at)
                            : "-"}
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
                  command={`ageval results upload-suite <dataset-root> --suite-run <id> --with-attempts`}
                />
                <p className="text-xs text-mute">
                  Or backfill one run:{" "}
                  <code className="font-mono">
                    ageval results upload &lt;db&gt; --run &lt;run_id&gt;
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
