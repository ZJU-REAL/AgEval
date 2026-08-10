import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Shell } from "@/components/layout";
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
  getOrg,
  listOrgMembers,
  listPackages,
  listResultShares,
  listSuites,
  type OrgMember,
  type OrgRow,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn, formatDate } from "@/lib/utils";

function latestByDatabase(items: PackageRelease[]): PackageRelease[] {
  const map = new Map<string, PackageRelease>();
  for (const row of items) {
    const prev = map.get(row.database_id);
    if (!prev || (row.created_at ?? 0) >= (prev.created_at ?? 0)) {
      map.set(row.database_id, row);
    }
  }
  return Array.from(map.values()).sort((a, b) =>
    a.database_id.localeCompare(b.database_id),
  );
}

type Tab = "overview" | "settings";

export function OrganizationDetailPage() {
  const { orgId: rawOrgId } = useParams();
  const orgId = rawOrgId ? decodeURIComponent(rawOrgId) : "";
  const token = getToken();
  const [tab, setTab] = useState<Tab>("overview");
  const [org, setOrg] = useState<OrgRow | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [datasets, setDatasets] = useState<PackageRelease[]>([]);
  const [sharedSuites, setSharedSuites] = useState<SuiteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orgId || !token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const [orgRow, memberRows, packages] = await Promise.all([
          getOrg(orgId, token),
          listOrgMembers(orgId, token),
          listPackages(token),
        ]);
        if (cancelled) return;
        setOrg(orgRow);
        setMembers(memberRows);
        setDatasets(
          latestByDatabase(packages).filter((p) => p.org_id === orgId),
        );
        setError(null);

        // Shared suite results: visible suites that list this org as a share target.
        try {
          const suites = await listSuites(null, token);
          const candidates = suites.slice(0, 80);
          const hits: SuiteRow[] = [];
          await Promise.all(
            candidates.map(async (s) => {
              if (!s.suite_run_id) return;
              try {
                const shares = await listResultShares(
                  "suite",
                  s.suite_run_id,
                  token,
                );
                const orgKey = orgId.toLowerCase();
                if (
                  shares.some(
                    (sh) =>
                      sh.target_type === "org" &&
                      sh.target_id.toLowerCase() === orgKey,
                  )
                ) {
                  hits.push(s);
                }
              } catch {
                // ignore unreadable share lists
              }
            }),
          );
          if (!cancelled) setSharedSuites(hits);
        } catch {
          if (!cancelled) setSharedSuites([]);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setOrg(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [orgId, token]);

  const title = useMemo(
    () => org?.display_name || org?.name || orgId,
    [org, orgId],
  );

  if (!token) {
    return (
      <Shell>
        <BreadcrumbNav
          items={[
            { label: "Organizations", href: "/organizations" },
            { label: orgId || "…" },
          ]}
          className="mb-4"
        />
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm">
          <p className="font-medium text-ink">Sign in required</p>
          <p className="mt-1 text-mute">
            <Link to="/login" className="underline underline-offset-2">
              Sign in
            </Link>{" "}
            to view this organization.
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Organizations", href: "/organizations" },
          { label: title },
        ]}
        className="mb-4"
      />

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load organization</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : (
        <>
          <div className="mb-4">
            <h1 className="text-2xl font-semibold tracking-tight text-ink">
              {title}
            </h1>
            <p className="font-mono text-sm text-mute mt-1">@{orgId}</p>
            {org?.role ? (
              <p className="text-xs text-body mt-1 capitalize">
                Your role: {org.role}
              </p>
            ) : null}
          </div>

          <div className="flex gap-1 border-b border-hairline mb-6">
            {(
              [
                ["overview", "Overview"],
                ["settings", "Settings"],
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

          {tab === "overview" ? (
            <div className="space-y-8">
              <section>
                <h2 className="text-sm font-medium text-ink mb-2">Members</h2>
                {members.length === 0 ? (
                  <p className="text-sm text-mute">No members listed.</p>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Member</TableHead>
                          <TableHead>Role</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {members.map((m) => (
                          <TableRow key={m.user_id}>
                            <TableCell className="font-mono text-sm">
                              @{m.user_id}
                            </TableCell>
                            <TableCell className="text-sm capitalize text-body">
                              {m.role}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="text-sm font-medium text-ink mb-2">Datasets</h2>
                {datasets.length === 0 ? (
                  <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                    No packages published under this org yet.
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Dataset</TableHead>
                          <TableHead>Version</TableHead>
                          <TableHead>Visibility</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {datasets.map((d) => (
                          <TableRow key={d.database_id}>
                            <TableCell>
                              <Link
                                to={`/datasets/${encodeDatasetId(d.database_id)}`}
                                className="font-mono text-sm hover:underline"
                              >
                                {d.database_id}
                              </Link>
                            </TableCell>
                            <TableCell className="font-mono text-xs text-body">
                              {d.version}
                            </TableCell>
                            <TableCell className="text-sm text-body">
                              {d.visibility}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="text-sm font-medium text-ink mb-2">
                  Shared results
                </h2>
                <p className="text-xs text-mute mb-2">
                  Suite results explicitly shared with this organization
                  (visible to you).
                </p>
                {sharedSuites.length === 0 ? (
                  <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                    No suite results have been shared with this organization
                    yet.
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Suite</TableHead>
                          <TableHead>Dataset</TableHead>
                          <TableHead>By</TableHead>
                          <TableHead>Updated</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sharedSuites.map((s) => (
                          <TableRow key={s.suite_run_id}>
                            <TableCell className="font-mono text-xs">
                              {s.suite_run_id}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-body">
                              {s.database_id ? (
                                <Link
                                  to={`/datasets/${encodeDatasetId(s.database_id)}`}
                                  className="hover:underline"
                                >
                                  {s.database_id}
                                </Link>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-mute">
                              {s.uploaded_by ? `@${s.uploaded_by}` : "—"}
                            </TableCell>
                            <TableCell className="text-xs text-mute">
                              {typeof s.created_at === "number"
                                ? formatDate(
                                    new Date(s.created_at * 1000).toISOString(),
                                  )
                                : typeof s.created_at === "string"
                                  ? formatDate(s.created_at)
                                  : "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>
            </div>
          ) : (
            <div className="space-y-8 max-w-2xl">
              <section>
                <h2 className="text-sm font-medium text-ink mb-1">
                  Organization description
                </h2>
                <p className="text-sm text-mute">
                  No description field on Registry yet. Display name:{" "}
                  <span className="text-body">
                    {org?.display_name || org?.name || "—"}
                  </span>
                  .
                </p>
              </section>
              <section>
                <h2 className="text-sm font-medium text-ink mb-1">Secrets</h2>
                <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                  Organization-scoped secrets (API keys for hosted jobs) are not
                  implemented in BORA Registry. Use host env / CLI credentials
                  instead.
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
