import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { LeaderboardTable } from "@/components/leaderboard-table";
import { Shell } from "@/components/layout";
import { Markdown } from "@/components/markdown";
import { VersionSwitcher } from "@/components/version-switcher";
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
  encodeDatasetId,
  getPackageByDigest,
  getPackageFile,
  hasSharedFiles,
  isPluginPackage,
  listPackageFiles,
  listPackageVersions,
  listSuites,
  pickPackageVersion,
  versionLabel,
  type FileItem,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
  taskIdsFromFiles,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree } from "@/lib/file-tree";
import { LEADERBOARD_K_FIXTURES } from "@/lib/leaderboard-fixtures";
import { cn, formatScore } from "@/lib/utils";

type Tab = "readme" | "tasks" | "shared" | "leaderboard";

function taskHasReadme(files: FileItem[], taskId: string): boolean {
  const path = `tasks/${taskId}/README.md`;
  return files.some((f) => f.type !== "dir" && f.path === path);
}

function taskJobStats(suites: SuiteRow[], taskId: string): {
  count: number;
  lastStatus: string | null;
  lastScore: number | null;
} {
  const hits: Array<{
    created: number;
    status: string | null;
    score: number | null;
  }> = [];
  for (const suite of suites) {
    const ref = (suite.task_refs || []).find((r) => r.task_id === taskId);
    if (!ref) continue;
    const created =
      typeof suite.created_at === "number"
        ? suite.created_at
        : Date.parse(String(suite.created_at || "")) || 0;
    hits.push({
      created,
      status: ref.status ?? null,
      score: ref.score ?? null,
    });
  }
  hits.sort((a, b) => b.created - a.created);
  const last = hits[0];
  return {
    count: hits.length,
    lastStatus: last?.status ?? null,
    lastScore: last?.score ?? null,
  };
}

export function DatasetDetailPage() {
  const navigate = useNavigate();
  const { datasetId: rawId } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const [search, setSearch] = useSearchParams();
  const tab = (search.get("tab") as Tab) || "readme";
  const requestedVersion = search.get("v");
  /** Local smoke: `?tab=leaderboard&demo=1` injects mock k-metric rows. */
  const demoLeaderboard = search.get("demo") === "1";

  const [versions, setVersions] = useState<PackageRelease[]>([]);
  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [readme, setReadme] = useState<string | null>(null);
  const [jobSuites, setJobSuites] = useState<SuiteRow[]>([]);
  const [boardSuites, setBoardSuites] = useState<SuiteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sharedSelected, setSharedSelected] = useState<string | null>(null);
  const [sharedContent, setSharedContent] = useState<string | null>(null);
  const [sharedNote, setSharedNote] = useState<string | null>(null);
  const [sharedFileLoading, setSharedFileLoading] = useState(false);
  const token = getToken();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const listed = await listPackageVersions(datasetId, token);
        if (!listed.length) {
          throw new RegistryHttpError(404, "not_found", "package not found");
        }
        const selected = pickPackageVersion(listed, requestedVersion);
        if (!selected) {
          throw new RegistryHttpError(404, "not_found", "package not found");
        }
        if (cancelled) return;
        setVersions(listed);
        let meta: PackageRelease = selected;
        try {
          meta = await getPackageByDigest(
            datasetId,
            selected.package_digest,
            token,
          );
        } catch {
          /* version list fields may already include package_kind */
        }
        if (isPluginPackage(meta) || isPluginPackage(selected)) {
          throw new RegistryHttpError(
            404,
            "not_found",
            "not a database package (open Plugin marketplace instead)",
          );
        }
        const chosen = meta.package_digest ? meta : selected;
        setRelease(chosen);
        const files = await listPackageFiles(
          datasetId,
          chosen.package_digest,
          token,
        );
        if (cancelled) return;
        setFileItems(files.items);
        setTaskIds(taskIdsFromFiles(files.items));
        if (hasSharedFiles(files.items)) {
          const prefer =
            files.items.find((e) => e.path === "shared/README.md") ||
            files.items.find(
              (e) => e.type !== "dir" && e.path.startsWith("shared/"),
            );
          if (prefer) setSharedSelected(prefer.path);
        } else {
          setSharedSelected(null);
        }
        try {
          const readmeFile = await getPackageFile(
            datasetId,
            chosen.package_digest,
            "README.md",
            token,
          );
          if (!cancelled) setReadme(decodeFileContent(readmeFile));
        } catch {
          if (!cancelled) setReadme(null);
        }
        try {
          const [jobs, board] = await Promise.all([
            listSuites(datasetId, token),
            listSuites(datasetId, token, { board: true }),
          ]);
          if (!cancelled) {
            setJobSuites(jobs);
            setBoardSuites(board);
          }
        } catch {
          if (!cancelled) {
            setJobSuites([]);
            setBoardSuites([]);
          }
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [datasetId, token, requestedVersion]);

  const lockCmd = useMemo(() => {
    if (!release) return `bora lock ${datasetId} --task <task_id>`;
    return `bora lock registry://${datasetId}@${release.version} --task <task_id>`;
  }, [datasetId, release]);

  const sharedPresent = useMemo(() => hasSharedFiles(fileItems), [fileItems]);
  const sharedTree = useMemo(
    () => buildNestedTree(fileItems, "shared"),
    [fileItems],
  );

  // Stale ?tab=shared when package has no shared/ → fall back to README.
  useEffect(() => {
    if (!loading && tab === "shared" && !sharedPresent) {
      setTab("readme");
    }
  }, [loading, tab, sharedPresent]);

  useEffect(() => {
    if (!release || !sharedSelected || tab !== "shared" || !sharedPresent) {
      setSharedContent(null);
      return;
    }
    let cancelled = false;
    setSharedFileLoading(true);
    setSharedNote(null);
    getPackageFile(datasetId, release.package_digest, sharedSelected, token)
      .then((f) => {
        if (cancelled) return;
        setSharedContent(decodeFileContent(f));
        if (f.truncated) {
          const full = f.size ?? 0;
          const shown = (f.content || "").length;
          setSharedNote(
            full > 0
              ? `Truncated preview: showing first ~${shown.toLocaleString()} of ${full.toLocaleString()} bytes (Hub preview cap).`
              : "Truncated preview (Hub preview size cap).",
          );
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSharedContent(null);
        if (err instanceof RegistryHttpError) {
          setSharedNote(`${err.code}: ${err.message}`);
        } else {
          setSharedNote(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setSharedFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, release, sharedSelected, token, tab]);

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

  function openTask(tid: string) {
    const qs = requestedVersion
      ? `?v=${encodeURIComponent(requestedVersion)}`
      : "";
    navigate(
      `/datasets/${encodeDatasetId(datasetId)}/tasks/${encodeURIComponent(tid)}${qs}`,
    );
  }

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Datasets", href: "/datasets" },
          { label: datasetId },
        ]}
        className="mb-4"
      />
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
            {datasetId}
          </h1>
          {release ? (
            <p className="text-sm text-mute mt-1">
              <span className="font-mono">{versionLabel(release)}</span> ·{" "}
              {release.visibility}
              {release.org_id ? (
                <>
                  {" "}
                  · org{" "}
                  <span className="font-mono text-xs text-body">{release.org_id}</span>
                </>
              ) : null}{" "}
              ·{" "}
              <span className="font-mono text-xs">
                {release.package_digest.slice(0, 19)}…
              </span>
            </p>
          ) : null}
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
        <CommandStrip command={lockCmd} />
      </div>

      <div className="flex gap-1 border-b border-hairline mb-4">
        {(
          [
            ["readme", "README"],
            ["tasks", "Tasks"],
            ...(sharedPresent
              ? ([["shared", "Shared"]] as Array<[Tab, string]>)
              : []),
            ["leaderboard", "Leaderboard"],
          ] as Array<[Tab, string]>
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

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="space-y-2 text-sm">
          <p className="text-error font-mono">{error}</p>
          {error.includes("Plugin marketplace") || error.includes("plugin") ? (
            <p className="text-body">
              <Link
                to={`/plugins/${encodeDatasetId(datasetId)}`}
                className="underline underline-offset-2"
              >
                Open in Plugin marketplace
              </Link>
            </p>
          ) : null}
        </div>
      ) : tab === "readme" ? (
        readme ? (
          <Markdown source={readme} />
        ) : (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-mute">
            No README.md in this package.
          </div>
        )
      ) : tab === "tasks" ? (
        taskIds.length === 0 ? (
          <p className="text-sm text-mute">No tasks/ members found.</p>
        ) : (
          <div className="rounded-[8px] border border-hairline overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Task</TableHead>
                  <TableHead>README</TableHead>
                  <TableHead>Recent jobs</TableHead>
                  <TableHead>Last result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {taskIds.map((tid) => {
                  const stats = taskJobStats(jobSuites, tid);
                  return (
                    <TableRow
                      key={tid}
                      className="cursor-pointer"
                      onClick={() => openTask(tid)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openTask(tid);
                        }
                      }}
                      tabIndex={0}
                      role="link"
                    >
                      <TableCell className="font-mono text-sm font-medium">
                        {tid}
                      </TableCell>
                      <TableCell className="text-sm text-body">
                        {taskHasReadme(fileItems, tid) ? "yes" : "no"}
                      </TableCell>
                      <TableCell className="tabular text-sm">
                        {stats.count}
                      </TableCell>
                      <TableCell className="text-sm tabular">
                        {stats.lastStatus
                          ? `${stats.lastStatus}${
                              stats.lastScore != null
                                ? ` · ${formatScore(stats.lastScore)}`
                                : ""
                            }`
                          : "-"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )
      ) : tab === "shared" && sharedPresent ? (
        <FileSplitPanel
          tree={sharedTree}
          treeLoading={false}
          selectedPath={sharedSelected}
          onSelect={setSharedSelected}
          fileContent={sharedContent}
          fileLoading={sharedFileLoading}
          fileNote={sharedNote}
          rootPrefix="shared"
        />
      ) : (
        <div className="space-y-2">
          {demoLeaderboard ? (
            <p className="text-xs text-mute">
              Demo fixtures loaded (
              <code className="font-mono">?demo=1</code>) — mock pass@k rows for
              local smoke only; not Registry data.
            </p>
          ) : null}
          <LeaderboardTable
            suites={demoLeaderboard ? LEADERBOARD_K_FIXTURES : boardSuites}
            databaseId={datasetId}
          />
        </div>
      )}
    </Shell>
  );
}
