import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { LoadingState } from "@/components/empty-state";
import { CatalogHead } from "@/components/page-head";
import { ListPager } from "@/components/list-pager";
import { UnderlineTabs } from "@/components/underline-tabs";
import { CommandStrip } from "@/components/command-strip";
import { DisplayNameEditor } from "@/components/display-name-editor";
import { FileSplitPanel } from "@/components/file-split-panel";
import { LeaderboardTable } from "@/components/leaderboard-table";
import { OfficialMark } from "@/components/official-mark";
import { OverlayFilePanel } from "@/components/overlay-file-panel";
import { Markdown } from "@/components/markdown";
import { PackageOwnerOps } from "@/components/package-owner-ops";
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
  getOrg,
  getPackageByDigest,
  getPackageFile,
  isPluginPackage,
  listPackageFiles,
  listPackageTasks,
  listPackageVersions,
  listSuites,
  pickPackageVersion,
  splitPackageId,
  updatePackageDisplayName,
  versionLabel,
  TASK_PAGE_SIZE,
  type FileItem,
  type PackageRelease,
  type PackageTaskRow,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getGithubUser, getToken } from "@/lib/auth";
import { buildNestedTree } from "@/lib/file-tree";
import { LEADERBOARD_K_FIXTURES } from "@/lib/leaderboard-fixtures";
import { formatScore } from "@/lib/utils";

type Tab = "readme" | "tasks" | "shared" | "overlays" | "leaderboard";
type BoardView = "public" | "internal";

function isInternalSuite(suite: SuiteRow): boolean {
  return suite.complete !== true || suite.bound_kind !== "release";
}

export function DatasetDetailPage() {
  const navigate = useNavigate();
  const { datasetId: rawId } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const [search, setSearch] = useSearchParams();
  const tab = (search.get("tab") as Tab) || "readme";
  const requestedVersion = search.get("v");
  const boardView: BoardView =
    search.get("board") === "internal" ? "internal" : "public";
  /** Local smoke: `?tab=leaderboard&demo=1` injects mock k-metric rows. */
  const demoLeaderboard = search.get("demo") === "1";

  const [versions, setVersions] = useState<PackageRelease[]>([]);
  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [taskRows, setTaskRows] = useState<PackageTaskRow[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [hasShared, setHasShared] = useState(false);
  const [flagsReady, setFlagsReady] = useState(false);
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [readme, setReadme] = useState<string | null>(null);
  const [jobSuites, setJobSuites] = useState<SuiteRow[]>([]);
  const [boardSuites, setBoardSuites] = useState<SuiteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [shellLoading, setShellLoading] = useState(true);
  const [readmeLoading, setReadmeLoading] = useState(false);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [sharedSelected, setSharedSelected] = useState<string | null>(null);
  const [sharedContent, setSharedContent] = useState<string | null>(null);
  const [sharedNote, setSharedNote] = useState<string | null>(null);
  const [sharedFileLoading, setSharedFileLoading] = useState(false);
  const [overlayPrefixes, setOverlayPrefixes] = useState<string[]>([]);
  const [canEditName, setCanEditName] = useState(false);
  const token = getToken();
  const packageParts = useMemo(() => splitPackageId(datasetId), [datasetId]);
  const taskOffsetRaw = Number.parseInt(search.get("offset") || "0", 10);
  const taskOffset =
    tab === "tasks" && Number.isFinite(taskOffsetRaw) && taskOffsetRaw > 0
      ? taskOffsetRaw
      : 0;

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setShellLoading(true);
      setError(null);
      setFlagsReady(false);
      setHasShared(false);
      setTaskRows([]);
      setTaskTotal(0);
      setReadme(null);
      setOverlayPrefixes([]);
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
            "not a dataset package (open Plugin marketplace instead)",
          );
        }
        if (meta.package_kind === "agent" || selected.package_kind === "agent") {
          throw new RegistryHttpError(
            404,
            "not_found",
            "not a dataset package (open Agent hub instead)",
          );
        }
        const chosen = meta.package_digest ? meta : selected;
        setRelease(chosen);
        if (token && chosen.org_id) {
          try {
            const org = await getOrg(chosen.org_id, token);
            if (!cancelled) {
              setCanEditName((org.role || "").toLowerCase() === "owner");
            }
          } catch {
            if (!cancelled) setCanEditName(false);
          }
        } else if (!cancelled) {
          setCanEditName(false);
        }
        if (!cancelled) setShellLoading(false);

        setReadmeLoading(true);
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
        } finally {
          if (!cancelled) setReadmeLoading(false);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setShellLoading(false);
        setReadmeLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [datasetId, token, requestedVersion]);

  const lockCmd = useMemo(() => {
    if (!release) return `ageval lock ${datasetId} --task <task_id>`;
    return `ageval lock registry://${datasetId}@${release.version} --task <task_id>`;
  }, [datasetId, release]);

  useEffect(() => {
    if (!release) return;
    let cancelled = false;
    setTasksLoading(true);
    listPackageTasks(datasetId, release.package_digest, token, {
      limit: TASK_PAGE_SIZE,
      offset: taskOffset,
    })
      .then((page) => {
        if (cancelled) return;
        setTaskRows(page.items);
        setTaskTotal(page.total);
        setHasShared(page.has_shared);
        setOverlayPrefixes(page.overlay_prefixes);
        setFlagsReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setTaskRows([]);
        setTaskTotal(0);
        setHasShared(false);
        setOverlayPrefixes([]);
        setFlagsReady(true);
      })
      .finally(() => {
        if (!cancelled) setTasksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, release, token, taskOffset]);

  useEffect(() => {
    if (!release || tab !== "leaderboard") return;
    let cancelled = false;
    Promise.all([
      listSuites(datasetId, token),
      listSuites(datasetId, token, { board: true }),
    ])
      .then(([jobs, board]) => {
        if (cancelled) return;
        setJobSuites(jobs);
        setBoardSuites(board);
      })
      .catch(() => {
        if (cancelled) return;
        setJobSuites([]);
        setBoardSuites([]);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, token, tab, release]);

  useEffect(() => {
    if (!release || tab !== "shared") return;
    let cancelled = false;
    listPackageFiles(datasetId, release.package_digest, token)
      .then((files) => {
        if (cancelled) return;
        setFileItems(files.items);
        const prefer =
          files.items.find((e) => e.path === "shared/README.md") ||
          files.items.find(
            (e) => e.type !== "dir" && e.path.startsWith("shared/"),
          );
        setSharedSelected(prefer?.path ?? null);
      })
      .catch(() => {
        if (!cancelled) setFileItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, release, token, tab]);

  const sharedPresent = hasShared;
  const overlaysPresent = overlayPrefixes.length > 0;
  const sharedTree = useMemo(
    () => buildNestedTree(fileItems, "shared"),
    [fileItems],
  );

  // Stale ?tab=shared|overlays when the package has neither → fall back to README.
  useEffect(() => {
    if (!flagsReady) return;
    if (tab === "shared" && !sharedPresent) setTab("readme");
    if (tab === "overlays" && !overlaysPresent) setTab("readme");
  }, [flagsReady, tab, sharedPresent, overlaysPresent]);

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
    if (next !== "leaderboard") {
      n.delete("board");
      n.delete("suite");
    }
    if (next !== "tasks") n.delete("offset");
    setSearch(n, { replace: true });
  }

  function setTaskOffset(next: number) {
    const n = new URLSearchParams(search);
    n.set("tab", "tasks");
    if (next <= 0) n.delete("offset");
    else n.set("offset", String(next));
    setSearch(n, { replace: true });
  }

  function setBoardView(next: BoardView) {
    const n = new URLSearchParams(search);
    n.set("tab", "leaderboard");
    if (next === "public") n.delete("board");
    else n.set("board", "internal");
    n.delete("suite");
    setSearch(n, { replace: true });
  }

  function setSuite(id: string | null) {
    const n = new URLSearchParams(search);
    n.set("tab", "leaderboard");
    if (id) n.set("suite", id);
    else n.delete("suite");
    setSearch(n, { replace: true });
  }

  const internalSuites = useMemo(
    () => jobSuites.filter(isInternalSuite),
    [jobSuites],
  );
  const login = (getGithubUser() || "").toLowerCase();
  const awaitingListing = useMemo(
    () =>
      jobSuites.filter(
        (row) =>
          Boolean(row.complete) &&
          row.bound_kind === "release" &&
          !row.board_listed &&
          (row.uploaded_by || "").toLowerCase() === login,
      ),
    [jobSuites, login],
  );
  const suiteQuery = search.get("suite");
  const publicSuites = useMemo(() => {
    if (!suiteQuery) return boardSuites;
    if (boardSuites.some((row) => row.suite_run_id === suiteQuery)) return boardSuites;
    const extra = jobSuites.find((row) => row.suite_run_id === suiteQuery);
    return extra ? [...boardSuites, extra] : boardSuites;
  }, [boardSuites, jobSuites, suiteQuery]);
  const awaitingListingVisible = useMemo(
    () =>
      awaitingListing.filter(
        (row) => !publicSuites.some((listed) => listed.suite_run_id === row.suite_run_id),
      ),
    [awaitingListing, publicSuites],
  );

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
    <>
      <CatalogHead
        title="Datasets"
        crumbs={[
          { label: "Datasets", href: "/datasets" },
          { label: datasetId },
        ]}
      />
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <DisplayNameEditor
            value={release?.display_name?.trim() || packageParts.name}
            prefix={packageParts.org ? `${packageParts.org}/` : null}
            canEdit={Boolean(token && canEditName && release)}
            headingClassName="text-xl font-semibold tracking-tight text-ink"
            afterTitle={release?.official ? <OfficialMark /> : null}
            onSave={async (next) => {
              const updated = await updatePackageDisplayName(
                datasetId,
                next,
                token,
              );
              setRelease((prev) =>
                prev
                  ? { ...prev, display_name: updated.display_name || next }
                  : prev,
              );
            }}
          />
          {release ? (
            <p className="text-xs text-mute mt-1">
              <span>{versionLabel(release)}</span> ·{" "}
              {release.visibility}
              {release.org_id ? (
                <>
                  {" "}
                  · org{" "}
                  <span>{release.org_id}</span>
                </>
              ) : null}{" "}
              ·{" "}
              <span>
                {release.package_digest.slice(0, 19)}…
              </span>
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {versions.length > 0 ? (
            <VersionSwitcher
              versions={versions}
              value={release?.version || versions[0].version}
              onChange={setVersion}
            />
          ) : null}
          {release ? (
            <PackageOwnerOps
              packageId={datasetId}
              release={release}
              canManage={canEditName}
              token={token}
              onUpdated={(next) => setRelease(next)}
              onDeleted={() => {
                const rest = versions.filter((v) => v.version !== release.version);
                if (!rest.length) {
                  navigate("/datasets");
                  return;
                }
                const next = pickPackageVersion(rest);
                setVersions(rest);
                if (next) setVersion(next.version);
              }}
              onReleased={(next) => {
                setRelease(next);
                setVersion(next.version);
              }}
            />
          ) : null}
        </div>
      </div>

      <div className="mb-4 max-w-3xl">
        <CommandStrip command={lockCmd} />
      </div>

      <UnderlineTabs
        className="mb-4"
        ariaLabel="Dataset sections"
        value={tab}
        onChange={setTab}
        items={[
          { id: "readme", label: "README" },
          { id: "tasks", label: "Tasks" },
          ...(sharedPresent
            ? ([{ id: "shared" as const, label: "Shared" }] as const)
            : []),
          ...(overlaysPresent
            ? ([{ id: "overlays" as const, label: "Overlays" }] as const)
            : []),
          { id: "leaderboard", label: "Leaderboard" },
        ]}
      />

      {shellLoading ? (
        <LoadingState label="Loading dataset" />
      ) : error ? (
        <div className="space-y-2 text-sm">
          <p className="text-error">{error}</p>
          {error.includes("Plugin marketplace") || error.includes("plugin") ? (
            <p className="text-body">
              <Link
                to={`/plugins/${encodeDatasetId(datasetId)}`}
                className="text-link hover:text-link-deep underline underline-offset-2"
              >
                Open in Plugin marketplace
              </Link>
            </p>
          ) : null}
          {error.includes("Agent hub") || error.includes("agent") ? (
            <p className="text-body">
              <Link
                to={`/agents/${encodeDatasetId(datasetId)}`}
                className="text-link hover:text-link-deep underline underline-offset-2"
              >
                Open in Agent hub
              </Link>
            </p>
          ) : null}
        </div>
      ) : tab === "readme" ? (
        readmeLoading ? (
          <p className="text-sm text-mute">Loading README…</p>
        ) : readme ? (
          <Markdown source={readme} />
        ) : (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-mute">
            No README.md in this package.
          </div>
        )
      ) : tab === "tasks" ? (
        tasksLoading && taskRows.length === 0 ? (
          <p className="text-sm text-mute">Loading tasks…</p>
        ) : taskTotal === 0 ? (
          <p className="text-sm text-mute">No tasks/ members found.</p>
        ) : (
          <div>
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
                {taskRows.map((row) => {
                  const tid = row.task_id;
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
                      <TableCell className="font-medium">
                        {tid}
                      </TableCell>
                      <TableCell className="text-body">
                        {row.has_readme ? "yes" : "no"}
                      </TableCell>
                      <TableCell className="tabular">
                        {row.job_count ?? 0}
                      </TableCell>
                      <TableCell className="tabular">
                        {row.last_status
                          ? `${row.last_status}${
                              row.last_score != null
                                ? ` · ${formatScore(row.last_score)}`
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
            <ListPager
              offset={taskOffset}
              limit={TASK_PAGE_SIZE}
              total={taskTotal}
              busy={tasksLoading}
              onOffset={setTaskOffset}
            />
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
      ) : tab === "overlays" && overlaysPresent && release ? (
        <div className="space-y-2">
          <p className="text-xs text-mute">
            Declared <code className="font-mono">overlays:</code> from package
            profiles. Prefix closure of the bound release. Read-only.
          </p>
          <OverlayFilePanel
            datasetId={datasetId}
            packageDigest={release.package_digest}
            prefixes={overlayPrefixes}
          />
        </div>
      ) : (
        <div className="space-y-3">
          {demoLeaderboard ? (
            <p className="text-xs text-mute">
              Demo fixtures loaded (
              <code className="font-mono">?demo=1</code>) — mock pass@k rows for
              local smoke only; not Registry data.
            </p>
          ) : (
            <UnderlineTabs
              size="sm"
              ariaLabel="Leaderboard visibility"
              value={boardView}
              onChange={setBoardView}
              items={[
                { id: "public", label: "Public" },
                { id: "internal", label: "Internal" },
              ]}
            />
          )}
          {boardView === "internal" && !demoLeaderboard ? (
            <p className="text-xs text-mute">
              Incomplete or draft-bound suite runs visible to you. Observational
              metrics only — not suite PASS. Public board still needs Dataset org listing approval.
            </p>
          ) : null}
          <LeaderboardTable
            suites={
              demoLeaderboard
                ? LEADERBOARD_K_FIXTURES
                : boardView === "internal"
                  ? internalSuites
                  : publicSuites
            }
            datasetId={datasetId}
            orgId={release?.org_id}
            packageDigest={release?.package_digest}
            versions={versions}
            onSuiteUpdated={(id, patch) => {
              const apply = (rows: SuiteRow[]) =>
                rows.map((row) =>
                  row.suite_run_id === id ? { ...row, ...patch } : row,
                );
              setJobSuites(apply);
              setBoardSuites(apply);
            }}
            onSuiteDeleted={(id) => {
              const drop = (rows: SuiteRow[]) =>
                rows.filter((row) => row.suite_run_id !== id);
              setJobSuites(drop);
              setBoardSuites(drop);
              if (search.get("suite") === id) setSuite(null);
            }}
            openSuiteId={demoLeaderboard ? null : search.get("suite")}
            onOpenSuite={demoLeaderboard ? undefined : setSuite}
            emptyTitle={
              boardView === "internal" && !demoLeaderboard
                ? "No internal suite runs"
                : undefined
            }
            emptyBody={
              boardView === "internal" && !demoLeaderboard
                ? "Caller-visible incomplete or draft-bound suite uploads appear here. Complete, release-bound rows stay on Public after listing approval. Task Jobs and attempt evidence are unchanged."
                : undefined
            }
          />
          {boardView === "public" && !demoLeaderboard && awaitingListingVisible.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs text-mute">
                Your complete release-bound suites that are not listed yet. Request
                listing from the settings menu Share modal; Dataset org owners
                decide in Inbox.
              </p>
              <LeaderboardTable
                suites={awaitingListingVisible}
                datasetId={datasetId}
                orgId={release?.org_id}
                packageDigest={release?.package_digest}
                versions={versions}
                onSuiteUpdated={(id, patch) => {
                  const apply = (rows: SuiteRow[]) =>
                    rows.map((row) =>
                      row.suite_run_id === id ? { ...row, ...patch } : row,
                    );
                  setJobSuites(apply);
                  setBoardSuites(apply);
                }}
                onSuiteDeleted={(id) => {
                  const drop = (rows: SuiteRow[]) =>
                    rows.filter((row) => row.suite_run_id !== id);
                  setJobSuites(drop);
                  setBoardSuites(drop);
                  if (search.get("suite") === id) setSuite(null);
                }}
                openSuiteId={search.get("suite")}
                onOpenSuite={setSuite}
              />
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}
