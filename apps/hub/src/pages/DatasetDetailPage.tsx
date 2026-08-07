import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
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
  listPackageFiles,
  listPackageVersions,
  listSuites,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
  taskIdsFromFiles,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Tab = "readme" | "tasks" | "leaderboard";

export function DatasetDetailPage() {
  const navigate = useNavigate();
  const { datasetId: rawId } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const [search, setSearch] = useSearchParams();
  const tab = (search.get("tab") as Tab) || "readme";

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [readme, setReadme] = useState<string | null>(null);
  const [suites, setSuites] = useState<SuiteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
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
        setTaskIds(taskIdsFromFiles(files.items));
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
            v{release.version} · {release.visibility} ·{" "}
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
      ) : (
        <LeaderboardTable suites={suites} databaseId={datasetId} />
      )}
    </Shell>
  );
}
