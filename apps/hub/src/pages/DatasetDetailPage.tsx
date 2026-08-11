import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { LeaderboardTable } from "@/components/leaderboard-table";
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
  encodeDatasetId,
  getPackageFile,
  hasSharedFiles,
  listPackageFiles,
  listPackageVersions,
  listSuites,
  type FileItem,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
  sharedFilesStats,
  taskIdsFromFiles,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree } from "@/lib/file-tree";
import { LEADERBOARD_K_FIXTURES } from "@/lib/leaderboard-fixtures";
import { cn } from "@/lib/utils";

type Tab = "readme" | "tasks" | "shared" | "leaderboard";

export function DatasetDetailPage() {
  const navigate = useNavigate();
  const { datasetId: rawId } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const [search, setSearch] = useSearchParams();
  const tab = (search.get("tab") as Tab) || "readme";
  /** Local smoke: `?tab=leaderboard&demo=1` injects mock k-metric rows (#60 C4). */
  const demoLeaderboard = search.get("demo") === "1";

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [readme, setReadme] = useState<string | null>(null);
  const [suites, setSuites] = useState<SuiteRow[]>([]);
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
        setFileItems(files.items);
        setTaskIds(taskIdsFromFiles(files.items));
        if (hasSharedFiles(files.items)) {
          const prefer =
            files.items.find((e) => e.path === "shared/README.md") ||
            files.items.find(
              (e) => e.type !== "dir" && e.path.startsWith("shared/"),
            );
          if (prefer) setSharedSelected(prefer.path);
        }
        try {
          const readmeFile = await getPackageFile(
            datasetId,
            latest.package_digest,
            "README.md",
            token,
          );
          if (!cancelled) setReadme(decodeFileContent(readmeFile));
        } catch {
          if (!cancelled) setReadme(null);
        }
        try {
          const suiteRows = await listSuites(datasetId, token);
          if (!cancelled) setSuites(suiteRows);
        } catch {
          if (!cancelled) setSuites([]);
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
  }, [datasetId, token]);

  const lockCmd = useMemo(() => {
    if (!release) return `bora lock ${datasetId} --task <task_id>`;
    return `bora lock registry://${datasetId}@${release.version} --task <task_id>`;
  }, [datasetId, release]);

  const sharedPresent = useMemo(() => hasSharedFiles(fileItems), [fileItems]);
  const sharedStats = useMemo(() => sharedFilesStats(fileItems), [fileItems]);
  const sharedTree = useMemo(
    () => buildNestedTree(fileItems, "shared"),
    [fileItems],
  );

  useEffect(() => {
    if (!release || !sharedSelected || tab !== "shared") {
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
        if (f.truncated) setSharedNote("truncated");
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

  function openTask(tid: string) {
    navigate(
      `/datasets/${encodeDatasetId(datasetId)}/tasks/${encodeURIComponent(tid)}`,
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
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
          {datasetId}
        </h1>
        {release ? (
          <p className="text-sm text-mute mt-1">
            v{release.version} · {release.visibility}
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

      <div className="mb-4 max-w-3xl">
        <CommandStrip command={lockCmd} />
      </div>

      <div className="flex gap-1 border-b border-hairline mb-4">
        {(
          [
            ["readme", "README"],
            ["tasks", "Tasks"],
            ["shared", "Shared"],
            ["leaderboard", "Leaderboard"],
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
            {id === "shared" && sharedPresent ? (
              <span className="ml-1.5 text-xs text-mute font-normal">
                {sharedStats.fileCount}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <p className="text-sm text-error font-mono">{error}</p>
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {taskIds.map((tid) => (
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
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )
      ) : tab === "shared" ? (
        !sharedPresent ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-mute space-y-2">
            <p className="text-ink font-medium">No Dataset-level shared/</p>
            <p>
              Optional <code className="font-mono">shared/</code> at the
              Database root is part of <code className="font-mono">packageDigest</code>{" "}
              when present. Cross-task code lives in{" "}
              <code className="font-mono">shared/lib</code>; domain fixtures in{" "}
              <code className="font-mono">shared/assets</code>.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-mute">
              Dataset <code className="font-mono">shared/**</code> ·{" "}
              {sharedStats.fileCount} file
              {sharedStats.fileCount === 1 ? "" : "s"} ·{" "}
              {sharedStats.totalBytes.toLocaleString()} bytes · in package digest
              (not Agent-mounted by default; gold stays under{" "}
              <code className="font-mono">tasks/*/evaluation/</code>)
            </p>
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
          </div>
        )
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
            suites={demoLeaderboard ? LEADERBOARD_K_FIXTURES : suites}
            databaseId={datasetId}
          />
        </div>
      )}
    </Shell>
  );
}
