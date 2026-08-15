import { useEffect, useState, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { OfficialMark } from "@/components/official-mark";
import { ScrollTable } from "@/components/scroll-table";
import {
  encodeDatasetId,
  latestPackageByDatabase,
  listOrgs,
  listPackageFiles,
  listPackages,
  listSuites,
  taskIdsFromFiles,
  packageDisplayTitle,
  versionLabel,
  type OrgRow,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getGithubUser, getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

const RETURN_KEY = "bora-hub-return";

type TaskRow = { databaseId: string; taskId: string };

export function rememberReturnPath(path: string): void {
  try {
    sessionStorage.setItem(RETURN_KEY, path);
  } catch {
    /* ignore */
  }
}

export function takeReturnPath(fallback = "/datasets"): string {
  try {
    const raw = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
    if (raw && raw.startsWith("/")) return raw;
  } catch {
    /* ignore */
  }
  return fallback;
}

export function HomePage() {
  const navigate = useNavigate();
  const token = getToken();
  const githubUser = getGithubUser();

  const [jobs, setJobs] = useState<SuiteRow[]>([]);
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [datasets, setDatasets] = useState<PackageRelease[]>([]);
  const [plugins, setPlugins] = useState<PackageRelease[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [taskNote, setTaskNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      listSuites(null, token, { uploadedBy: "me" }),
      listOrgs(token),
      listPackages(token, { packageKind: "database", mine: true }),
      listPackages(token, { packageKind: "plugin", mine: true }),
    ])
      .then(async ([suiteRows, orgRows, datasetRows, pluginRows]) => {
        if (cancelled) return;
        const ds = latestPackageByDatabase(datasetRows);
        const plugs = latestPackageByDatabase(pluginRows);
        setJobs(suiteRows);
        setOrgs(orgRows);
        setDatasets(ds);
        setPlugins(plugs);
        setTaskNote(null);
        setError(null);

        const listings = await Promise.all(
          ds.map(async (row) => {
            try {
              const files = await listPackageFiles(
                row.database_id,
                row.package_digest,
                token,
              );
              return {
                ok: true as const,
                databaseId: row.database_id,
                ids: taskIdsFromFiles(files.items),
              };
            } catch {
              return {
                ok: false as const,
                databaseId: row.database_id,
                ids: [] as string[],
              };
            }
          }),
        );
        const taskRows: TaskRow[] = [];
        const seen = new Set<string>();
        function addTask(databaseId: string, taskId: string) {
          const key = `${databaseId}/${taskId}`;
          if (seen.has(key)) return;
          seen.add(key);
          taskRows.push({ databaseId, taskId });
        }
        for (const listing of listings) {
          for (const tid of listing.ids) addTask(listing.databaseId, tid);
        }
        const maintainable = new Set(ds.map((d) => d.database_id));
        if (!taskRows.length) {
          for (const s of suiteRows) {
            if (!s.database_id || !maintainable.has(s.database_id)) continue;
            for (const ref of s.task_refs || []) {
              const tid = String(ref.task_id || "").trim();
              if (tid) addTask(s.database_id, tid);
            }
          }
        }
        const filesFailed = ds.length > 0 && listings.every((r) => !r.ok);
        if (!cancelled) {
          setTasks(taskRows);
          setTaskNote(
            filesFailed && !taskRows.length
              ? "Could not list task members from dataset files."
              : null,
          );
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!token) {
    rememberReturnPath("/home");
    return <Navigate to="/login" replace />;
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Home</h1>
        <p className="text-sm text-body mt-1">
          {githubUser ? (
            <>
              Signed in as{" "}
              <span className="inline-flex items-center gap-1 align-middle">
                <span className="font-mono text-xs">{githubUser}</span>
                {orgs.some((o) => o.official) ? (
                  <OfficialMark kind="org" />
                ) : null}
              </span>
              {" · "}
            </>
          ) : null}
          Read-only lists. Publish, upload, and release stay on the CLI.
        </p>
      </div>

      {loading ? <p className="text-sm text-mute">Loading…</p> : null}
      {error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm mb-4">
          <p className="text-error font-medium">Could not load home</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="space-y-8">
          <HomeSection
            title="Organizations"
            hint="Membership only."
            empty="You do not belong to an organization yet."
            count={orgs.length}
          >
            {orgs.length ? (
              <ScrollTable
                headers={["Org", "Role"]}
                rows={orgs.map((o) => ({
                  key: o.org_id,
                  onClick: () =>
                    navigate(`/organizations/${encodeURIComponent(o.org_id)}`),
                  cells: [
                    <span key="id" className="inline-flex items-center gap-1.5 min-w-0">
                      <span className="font-mono text-sm">{o.org_id}</span>
                      {o.display_name ? (
                        <span className="text-mute text-xs">
                          {o.display_name}
                        </span>
                      ) : null}
                      {o.official ? <OfficialMark kind="org" /> : null}
                    </span>,
                    o.role || "—",
                  ],
                }))}
              />
            ) : null}
          </HomeSection>

          <HomeSection
            title="Datasets"
            hint="Datasets you can maintain (owner or collaborator)."
            empty="No maintainable datasets yet."
            count={datasets.length}
          >
            {datasets.length ? (
              <ScrollTable
                headers={["Dataset", "Version", "Visibility"]}
                rows={datasets.map((d) => ({
                  key: d.database_id,
                  onClick: () =>
                    navigate(`/datasets/${encodeDatasetId(d.database_id)}`),
                  cells: [
                    <span key="id" className="font-mono text-sm">
                      {d.database_id}
                    </span>,
                    versionLabel(d),
                    d.visibility,
                  ],
                }))}
              />
            ) : null}
          </HomeSection>

          <HomeSection
            title="Tasks"
            hint="Members of datasets you can maintain."
            empty={
              taskNote || "No tasks in your maintainable datasets."
            }
            count={tasks.length}
          >
            {tasks.length ? (
              <ScrollTable
                headers={["Dataset", "Task"]}
                rows={tasks.map((t) => ({
                  key: `${t.databaseId}/${t.taskId}`,
                  onClick: () =>
                    navigate(
                      `/datasets/${encodeDatasetId(t.databaseId)}/tasks/${encodeURIComponent(t.taskId)}`,
                    ),
                  cells: [
                    <span key="db" className="font-mono text-xs">
                      {t.databaseId}
                    </span>,
                    <span key="t" className="font-mono text-sm">
                      {t.taskId}
                    </span>,
                  ],
                }))}
              />
            ) : null}
          </HomeSection>

          <HomeSection
            title="Plugins"
            hint="Plugin packages you uploaded."
            empty="No plugin packages uploaded by this account."
            count={plugins.length}
          >
            {plugins.length ? (
              <ScrollTable
                headers={["Plugin", "Version"]}
                rows={plugins.map((p) => ({
                  key: p.database_id,
                  onClick: () =>
                    navigate(`/plugins/${encodeDatasetId(p.database_id)}`),
                  cells: [
                    <span
                      key="id"
                      className="inline-flex items-center gap-1.5 min-w-0"
                    >
                      <span className="font-mono text-sm truncate">
                        {packageDisplayTitle(p.database_id, p.display_name)}
                      </span>
                      {p.official ? <OfficialMark /> : null}
                    </span>,
                    `v${p.version}`,
                  ],
                }))}
              />
            ) : null}
          </HomeSection>

          <HomeSection
            title="Jobs"
            hint="Suites you uploaded (uploaded_by), not every job in your orgs."
            empty="No suite uploads under this account yet."
            count={jobs.length}
          >
            {jobs.length ? (
              <ScrollTable
                headers={["Suite", "Dataset", "Pass rate", "Uploaded"]}
                rows={jobs.map((s) => ({
                  key: s.suite_run_id,
                  onClick: () => {
                    if (!s.database_id) return;
                    const tid = (s.task_refs || []).find((r) => r.task_id)
                      ?.task_id;
                    const ds = `/datasets/${encodeDatasetId(s.database_id)}`;
                    navigate(
                      tid
                        ? `${ds}/tasks/${encodeURIComponent(tid)}?tab=jobs`
                        : `${ds}?tab=leaderboard`,
                    );
                  },
                  cells: [
                    <span key="id" className="font-mono text-xs">
                      {s.suite_run_id}
                    </span>,
                    s.database_id || "—",
                    s.pass_rate == null
                      ? "—"
                      : `${(Number(s.pass_rate) * 100).toFixed(1)}%`,
                    typeof s.created_at === "number"
                      ? formatDate(new Date(s.created_at * 1000).toISOString())
                      : "—",
                  ],
                }))}
              />
            ) : null}
          </HomeSection>
        </div>
      ) : null}
    </>
  );
}

function HomeSection({
  title,
  hint,
  empty,
  count,
  children,
}: {
  title: string;
  hint: string;
  empty: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium text-ink">{title}</h2>
        <span className="text-[11px] tabular-nums text-mute">{count}</span>
      </div>
      <p className="text-xs text-mute">{hint}</p>
      {count === 0 ? (
        <p className="text-sm text-mute rounded-[8px] border border-dashed border-hairline bg-canvas-soft px-3 py-4">
          {empty}
        </p>
      ) : (
        children
      )}
    </section>
  );
}


