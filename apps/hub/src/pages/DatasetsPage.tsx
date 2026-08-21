import { Database } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { CatalogScopeBar } from "@/components/catalog-scope-bar";
import { PageHead } from "@/components/page-head";
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
  isDatasetPackage,
  listOrgs,
  latestPackageByDataset,
  listPackages,
  packageDisplayTitle,
  versionLabel,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

type Scope = "orgs" | "explore";

export function DatasetsPage() {
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
    // Datasets surface must not list package_kind=plugin.
    const packagesP = listPackages(token, { packageKind: "dataset" });
    const orgsP = token
      ? listOrgs(token).catch(() => [] as Awaited<ReturnType<typeof listOrgs>>)
      : Promise.resolve([]);

    Promise.all([packagesP, orgsP])
      .then(([rows, orgs]) => {
        if (cancelled) return;
        setItems(rows.filter(isDatasetPackage));
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

  const datasets = useMemo(() => {
    const latest = latestPackageByDataset(items);
    const scoped =
      scope === "orgs"
        ? latest.filter(
            (r) => r.org_id && myOrgIds.has(r.org_id) && token,
          )
        : latest.filter((r) => r.visibility === "public");
    const q = query.trim().toLowerCase();
    if (!q) return scoped;
    return scoped.filter(
      (r) =>
        r.dataset_id.toLowerCase().includes(q) ||
        packageDisplayTitle(r.dataset_id, r.display_name)
          .toLowerCase()
          .includes(q) ||
        (r.org_id && r.org_id.toLowerCase().includes(q)),
    );
  }, [items, scope, myOrgIds, query, token]);

  function setScope(next: Scope) {
    setSearchParams(next === "explore" ? { scope: "explore" } : {}, {
      replace: true,
    });
  }

  function openDataset(id: string) {
    navigate(`/datasets/${encodeDatasetId(id)}`);
  }

  return (
    <>
      <PageHead
        title={scope === "orgs" ? "Your datasets" : "Explore datasets"}
        sub={
          scope === "orgs"
            ? "Packages published by organizations you belong to."
            : "Public packages on this Registry."
        }
      />

      <CatalogScopeBar
        scope={scope}
        onScope={setScope}
        query={query}
        onQuery={setQuery}
        searchLabel="Search datasets"
        searchPlaceholder="Search datasets…"
      />

      {scope === "orgs" && !token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">Sign in to see org packages</p>
          <p className="mt-1 text-mute">
            <SignInLink /> to list datasets from your organizations. Public
            packages are under{" "}
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
          <p className="text-error font-medium">Could not load packages</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
        </div>
      ) : (
        <>
          {datasets.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm text-body">
              <div className="flex justify-center mb-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
                  <Database className="h-8 w-8" strokeWidth={1.5} aria-hidden />
                </div>
              </div>
              <p className="font-medium text-ink">No datasets found</p>
              <p className="mt-1 text-mute">
                {scope === "orgs"
                  ? "No packages from your organizations yet. Publish with ageval publish --org <id>."
                  : "No public packages on this Registry yet."}
              </p>
            </div>
          ) : (
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Dataset</TableHead>
                    <TableHead>Org</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead className="text-right tabular-nums">Size</TableHead>
                    <TableHead>Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {datasets.map((row) => (
                    <TableRow
                      key={`${row.dataset_id}@${row.version}`}
                      className="cursor-pointer"
                      onClick={() => openDataset(row.dataset_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openDataset(row.dataset_id);
                        }
                      }}
                      tabIndex={0}
                      role="link"
                    >
                      <TableCell className="font-medium font-mono text-sm">
                        {packageDisplayTitle(row.dataset_id, row.display_name)}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-mute">
                        {row.org_id ? (
                          <Link
                            to={`/organizations/${encodeURIComponent(row.org_id)}`}
                            className="hover:text-ink"
                            onClick={(e) => e.stopPropagation()}
                          >
                            @{row.org_id}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-body">
                        {versionLabel(row)}
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
            {datasets.length} dataset{datasets.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
