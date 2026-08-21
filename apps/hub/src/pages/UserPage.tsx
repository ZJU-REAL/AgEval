import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHead } from "@/components/page-head";
import { OfficialMark } from "@/components/official-mark";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  encodeDatasetId,
  getUser,
  latestPackageByDataset,
  listPackages,
  packageDisplayTitle,
  versionLabel,
  type PackageRelease,
  type UserPublic,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

export function UserPage() {
  const { login: rawLogin } = useParams();
  const login = rawLogin ? decodeURIComponent(rawLogin) : "";
  const token = getToken();

  const [user, setUser] = useState<UserPublic | null>(null);
  const [datasets, setDatasets] = useState<PackageRelease[]>([]);
  const [plugins, setPlugins] = useState<PackageRelease[]>([]);
  const [agents, setAgents] = useState<PackageRelease[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!login) {
      setLoading(false);
      setError("not_found: user not found");
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const profile = await getUser(login);
        if (cancelled) return;
        setUser(profile);
        setError(null);
        const uid = profile.user_id;
        const [datasetRows, pluginRows, agentRows] = await Promise.all([
          listPackages(token, { packageKind: "dataset" }).catch(
            () => [] as PackageRelease[],
          ),
          listPackages(token, { packageKind: "plugin" }).catch(
            () => [] as PackageRelease[],
          ),
          listPackages(token, { packageKind: "agent" }).catch(
            () => [] as PackageRelease[],
          ),
        ]);
        if (cancelled) return;
        const mine = (rows: PackageRelease[]) =>
          latestPackageByDataset(rows).filter(
            (row) =>
              row.visibility === "public" &&
              (row.uploaded_by || "").toLowerCase() === uid,
          );
        setDatasets(mine(datasetRows));
        setPlugins(mine(pluginRows));
        setAgents(mine(agentRows));
      } catch (err: unknown) {
        if (cancelled) return;
        setUser(null);
        setDatasets([]);
        setPlugins([]);
        setAgents([]);
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [login, token]);

  const title = useMemo(
    () => user?.display_name || user?.user_id || login,
    [user, login],
  );
  const avatar =
    user?.avatar_url ||
    (user?.user_id
      ? `https://github.com/${encodeURIComponent(user.user_id)}.png?size=64`
      : "");

  return (
    <>
      <PageHead title={title || "…"} />

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load user</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : user ? (
        <div className="space-y-8">
          <div className="flex items-center gap-3 min-w-0">
            {avatar ? (
              <img
                src={avatar}
                alt=""
                width={48}
                height={48}
                className="h-12 w-12 rounded-full border border-hairline bg-canvas-soft object-cover shrink-0"
              />
            ) : null}
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight text-ink inline-flex items-center gap-1.5 min-w-0">
                <span className="truncate">{title}</span>
                {user.official ? <OfficialMark kind="org" /> : null}
              </h1>
              <p className="font-mono text-sm text-mute mt-1">
                @{user.user_id}
              </p>
            </div>
          </div>

          {user.official_orgs.length ? (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-ink">
                Official organizations
              </h2>
              <div className="rounded-[8px] border border-hairline overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Organization</TableHead>
                      <TableHead>ID</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {user.official_orgs.map((org) => (
                      <TableRow key={org.org_id}>
                        <TableCell>
                          <Link
                            to={`/organizations/${encodeURIComponent(org.org_id)}`}
                            className="inline-flex items-center gap-1.5 hover:underline"
                          >
                            <span>
                              {org.display_name || org.org_id}
                            </span>
                            <OfficialMark kind="org" />
                          </Link>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-mute">
                          @{org.org_id}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          ) : null}

          <UserPackageSection
            title="Public datasets"
            empty="No public datasets uploaded by this account."
            rows={datasets}
            href={(row) => `/datasets/${encodeDatasetId(row.dataset_id)}`}
          />
          <UserPackageSection
            title="Public plugins"
            empty="No public plugins uploaded by this account."
            rows={plugins}
            href={(row) => `/plugins/${encodeDatasetId(row.dataset_id)}`}
            kind="plugin"
          />
          <UserPackageSection
            title="Public agents"
            empty="No public agents uploaded by this account."
            rows={agents}
            href={(row) => `/agents/${encodeDatasetId(row.dataset_id)}`}
            kind="agent"
          />
        </div>
      ) : null}
    </>
  );
}

function UserPackageSection({
  title,
  empty,
  rows,
  href,
  kind = "dataset",
}: {
  title: string;
  empty: string;
  rows: PackageRelease[];
  href: (row: PackageRelease) => string;
  kind?: "dataset" | "plugin" | "agent";
}) {
  const head =
    kind === "plugin" ? "Plugin" : kind === "agent" ? "Agent" : "Dataset";
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      {rows.length === 0 ? (
        <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
          {empty}
        </div>
      ) : (
        <div className="rounded-[8px] border border-hairline overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{head}</TableHead>
                <TableHead>Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.dataset_id}>
                  <TableCell>
                    <Link
                      to={href(row)}
                      className="inline-flex items-center gap-1.5 font-mono text-sm hover:underline min-w-0"
                    >
                      <span className="truncate">
                        {packageDisplayTitle(row.dataset_id, row.display_name)}
                      </span>
                      {kind !== "dataset" && row.official ? (
                        <OfficialMark />
                      ) : null}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-body">
                    {versionLabel(row)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}
