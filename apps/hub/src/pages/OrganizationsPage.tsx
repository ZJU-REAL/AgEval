import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Shell } from "@/components/layout";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  listOrgs,
  listPackages,
  type OrgRow,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

function latestByDatabase(items: PackageRelease[]): PackageRelease[] {
  const map = new Map<string, PackageRelease>();
  for (const row of items) {
    const prev = map.get(row.database_id);
    if (!prev || (row.created_at ?? 0) >= (prev.created_at ?? 0)) {
      map.set(row.database_id, row);
    }
  }
  return Array.from(map.values());
}

export function OrganizationsPage() {
  const navigate = useNavigate();
  const token = getToken();
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [packages, setPackages] = useState<PackageRelease[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setOrgs([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([listOrgs(token), listPackages(token)])
      .then(([orgRows, pkgRows]) => {
        if (cancelled) return;
        setOrgs(orgRows);
        setPackages(pkgRows);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setOrgs([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const datasetCountByOrg = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of latestByDatabase(packages)) {
      if (!row.org_id) continue;
      counts.set(row.org_id, (counts.get(row.org_id) ?? 0) + 1);
    }
    return counts;
  }, [packages]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return orgs;
    return orgs.filter(
      (o) =>
        o.org_id.toLowerCase().includes(q) ||
        (o.display_name || "").toLowerCase().includes(q) ||
        (o.name || "").toLowerCase().includes(q),
    );
  }, [orgs, query]);

  return (
    <Shell>
      <BreadcrumbNav items={[{ label: "Organizations" }]} className="mb-4" />
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Organizations
        </h1>
        <p className="text-sm text-body mt-1">
          Organizations you belong to. Packages are published under an org.
        </p>
      </div>

      {!token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">Sign in required</p>
          <p className="mt-1 text-mute">
            <Link to="/login" className="underline underline-offset-2">
              Sign in
            </Link>{" "}
            to list your organizations.
          </p>
        </div>
      ) : loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load organizations</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : (
        <>
          <div className="mb-3 max-w-md">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your organizations…"
              aria-label="Search organizations"
            />
          </div>
          {filtered.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm">
              <p className="font-medium text-ink">No organizations</p>
              <p className="mt-1 text-mute">
                Create one with{" "}
                <code className="font-mono text-xs">
                  bora registry org-create &lt;name&gt;
                </code>
                .
              </p>
            </div>
          ) : (
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Organization</TableHead>
                    <TableHead>ID</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead className="text-right tabular-nums">
                      Datasets
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((org) => (
                    <TableRow
                      key={org.org_id}
                      className="cursor-pointer"
                      onClick={() =>
                        navigate(
                          `/organizations/${encodeURIComponent(org.org_id)}`,
                        )
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(
                            `/organizations/${encodeURIComponent(org.org_id)}`,
                          );
                        }
                      }}
                      tabIndex={0}
                      role="link"
                    >
                      <TableCell className="font-medium text-ink">
                        {org.display_name || org.name || org.org_id}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-mute">
                        @{org.org_id}
                      </TableCell>
                      <TableCell className="text-body capitalize text-sm">
                        {org.role || "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-body">
                        {datasetCountByOrg.get(org.org_id) ?? 0}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-xs text-mute mt-3 tabular-nums">
            {filtered.length} organization
            {filtered.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </Shell>
  );
}
