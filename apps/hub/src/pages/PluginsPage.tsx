import { Puzzle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { CatalogScopeBar } from "@/components/catalog-scope-bar";
import { OfficialMark } from "@/components/official-mark";
import { SignInLink } from "@/components/sign-in-button";
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
  listOrgs,
  listPackages,
  packageDisplayTitle,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

/** Collapse multi-version list to latest per package id (by created_at). */
function latestByPackage(items: PackageRelease[]): PackageRelease[] {
  const map = new Map<string, PackageRelease>();
  for (const row of items) {
    const prev = map.get(row.database_id);
    if (!prev) {
      map.set(row.database_id, row);
      continue;
    }
    const a = prev.created_at ?? 0;
    const b = row.created_at ?? 0;
    if (b >= a) map.set(row.database_id, row);
  }
  return Array.from(map.values()).sort((x, y) =>
    x.database_id.localeCompare(y.database_id),
  );
}

type Scope = "orgs" | "explore";

export function PluginsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const scope: Scope =
    searchParams.get("scope") === "explore" ? "explore" : "orgs";

  const [items, setItems] = useState<PackageRelease[]>([]);
  const [myOrgIds, setMyOrgIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const token = getToken();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const packagesP = listPackages(token, { packageKind: "plugin" });
    const orgsP = token
      ? listOrgs(token).catch(() => [] as Awaited<ReturnType<typeof listOrgs>>)
      : Promise.resolve([]);

    Promise.all([packagesP, orgsP])
      .then(([rows, orgs]) => {
        if (cancelled) return;
        setItems(rows);
        setMyOrgIds(new Set(orgs.map((o) => o.org_id)));
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const plugins = useMemo(() => {
    const latest = latestByPackage(items);
    const scoped =
      scope === "orgs"
        ? latest.filter((r) => r.org_id && myOrgIds.has(r.org_id) && token)
        : latest.filter((r) => r.visibility === "public");
    const q = query.trim().toLowerCase();
    if (!q) return scoped;
    return scoped.filter(
      (r) =>
        r.database_id.toLowerCase().includes(q) ||
        (r.org_id && r.org_id.toLowerCase().includes(q)),
    );
  }, [items, scope, myOrgIds, query, token]);

  function setScope(next: Scope) {
    setSearchParams(next === "explore" ? { scope: "explore" } : {}, {
      replace: true,
    });
  }

  function openPlugin(id: string) {
    navigate(`/plugins/${encodeDatasetId(id)}`);
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Plugin marketplace
        </h1>
        <p className="text-sm text-body mt-1">
          Browse{" "}
          <span className="font-mono text-xs">bora.plugin/1</span> packages.
          Install is CLI-only (Recognition only — does not change profiles).
        </p>
      </div>

      <CatalogScopeBar
        scope={scope}
        onScope={setScope}
        query={query}
        onQuery={setQuery}
        searchLabel="Search plugins"
        searchPlaceholder="Search plugins…"
      />

      {scope === "orgs" && !token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">Sign in to see org plugins</p>
          <p className="mt-1 text-mute">
            <SignInLink /> to list plugins from your organizations. Public
            plugins are under{" "}
            <button
              type="button"
              className="underline underline-offset-2"
              onClick={() => setScope("explore")}
            >
              Explore
            </button>
            .
          </p>
        </div>
      ) : loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm text-body">
          <p className="text-error font-medium">Could not load plugins</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
        </div>
      ) : (
        <>
          {plugins.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm text-body">
              <div className="flex justify-center mb-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
                  <Puzzle className="h-8 w-8" strokeWidth={1.5} aria-hidden />
                </div>
              </div>
              <p className="font-medium text-ink">No plugins found</p>
              <p className="mt-1 text-mute max-w-md mx-auto">
                {scope === "orgs"
                  ? "No plugin packages from your organizations yet. Publish with bora plugin publish <path> --org <id>."
                  : "No public plugin packages on this Registry yet."}
              </p>
            </div>
          ) : (
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Plugin</TableHead>
                    <TableHead>Org</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead className="text-right tabular-nums">Size</TableHead>
                    <TableHead>Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {plugins.map((row) => (
                    <TableRow
                      key={`${row.database_id}@${row.version}`}
                      className="cursor-pointer"
                      onClick={() => openPlugin(row.database_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openPlugin(row.database_id);
                        }
                      }}
                      tabIndex={0}
                      role="link"
                    >
                      <TableCell className="font-medium font-mono text-sm">
                        <span className="inline-flex items-center gap-1.5 min-w-0">
                          <span className="truncate">
                            {packageDisplayTitle(
                              row.database_id,
                              row.display_name,
                            )}
                          </span>
                          {row.official ? <OfficialMark /> : null}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-mute">
                        {row.org_id ? (
                          <span className="inline-flex items-center gap-1">
                            <Link
                              to={`/organizations/${encodeURIComponent(row.org_id)}`}
                              className="hover:text-ink"
                              onClick={(e) => e.stopPropagation()}
                            >
                              @{row.org_id}
                            </Link>
                            {row.official ? <OfficialMark kind="org" /> : null}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-body">
                        {row.version}
                      </TableCell>
                      <TableCell className="text-body">{row.visibility}</TableCell>
                      <TableCell className="text-right tabular-nums text-body">
                        {row.size.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-mute text-xs">
                        {typeof row.created_at === "number"
                          ? formatDate(
                              new Date(row.created_at * 1000).toISOString(),
                            )
                          : "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-xs text-mute mt-3 tabular-nums">
            {plugins.length} plugin{plugins.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
