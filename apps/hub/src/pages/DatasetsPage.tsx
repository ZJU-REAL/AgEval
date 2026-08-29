import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import {
  CatalogScopeBar,
  DATASET_SCOPE_ITEMS,
  catalogListOpts,
  catalogScopeFromSearch,
  catalogScopeSearch,
  type CatalogScope,
} from "@/components/catalog-scope-bar";
import {
  CatalogEmpty,
  CatalogLoading,
} from "@/components/empty-state";
import { PageHead } from "@/components/page-head";
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
  latestPackageByDataset,
  listPackages,
  packageDisplayTitle,
  versionLabel,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { sortRows, useTableSort } from "@/components/sortable-head";
import { TableColumnPicker } from "@/components/ui/table-column-picker";
import { useTableColumns } from "@/hooks/use-table-columns";
import { formatDate } from "@/lib/utils";

const DATASET_OPTIONAL_COLUMNS = [
  { id: "updated", label: "Updated" },
] as const;
const DATASET_OPTIONAL_IDS = DATASET_OPTIONAL_COLUMNS.map((col) => col.id);
const DATASET_OPTIONAL_DEFAULT: typeof DATASET_OPTIONAL_IDS = ["updated"];

const STICKY_TH = "sticky top-0 z-10";

export function DatasetsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const scope = catalogScopeFromSearch(searchParams, false);

  const [items, setItems] = useState<PackageRelease[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [columns, setColumns] = useTableColumns(
    "ageval.hub.columns.datasets",
    DATASET_OPTIONAL_IDS,
    DATASET_OPTIONAL_DEFAULT,
  );
  const sort = useTableSort();
  const token = getToken();
  const needsAuth = scope === "orgs";

  useEffect(() => {
    if (needsAuth && !token) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listPackages(token, { packageKind: "dataset", ...catalogListOpts(scope) })
      .then((rows) => {
        if (cancelled) return;
        setItems(rows.filter(isDatasetPackage));
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
  }, [token, scope, needsAuth]);

  useEffect(() => {
    if (sort.sortKey === "updated" && !columns.includes("updated")) {
      sort.setSortKey(null);
      sort.setSortDir(null);
    }
  }, [columns, sort.sortKey, sort.setSortKey, sort.setSortDir]);

  const datasets = useMemo(() => {
    const latest = latestPackageByDataset(items);
    const q = query.trim().toLowerCase();
    const filtered = !q
      ? latest
      : latest.filter(
          (r) =>
            r.dataset_id.toLowerCase().includes(q) ||
            packageDisplayTitle(r.dataset_id, r.display_name)
              .toLowerCase()
              .includes(q) ||
            (r.org_id && r.org_id.toLowerCase().includes(q)),
        );
    return sortRows(filtered, sort.sortKey, sort.sortDir, (row, key) => {
      switch (key) {
        case "dataset":
          return packageDisplayTitle(row.dataset_id, row.display_name);
        case "org":
          return row.org_id || "";
        case "version":
          return versionLabel(row);
        case "visibility":
          return row.visibility || "";
        case "tasks":
          return typeof row.task_count === "number" ? row.task_count : null;
        case "updated":
          return row.created_at ?? null;
        default:
          return null;
      }
    });
  }, [items, query, sort.sortKey, sort.sortDir]);

  function setScope(next: CatalogScope) {
    setSearchParams(catalogScopeSearch(next), { replace: true });
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

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="shrink-0 pb-3">
          <CatalogScopeBar
            variant="select"
            scope={scope}
            onScope={setScope}
            items={DATASET_SCOPE_ITEMS}
            query={query}
            onQuery={setQuery}
            searchLabel="Search datasets"
            searchPlaceholder="Search datasets…"
            end={
              <TableColumnPicker
                options={DATASET_OPTIONAL_COLUMNS}
                value={columns}
                onChange={setColumns}
                ariaLabel="Optional dataset columns"
              />
            }
            className="mb-0"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {scope === "orgs" && !token ? (
        <CatalogEmpty
          kind="dataset"
          scope={scope}
          signedIn={false}
          searching={false}
          onExplore={() => setScope("explore")}
          onClearSearch={() => setQuery("")}
        />
      ) : loading ? (
        <CatalogLoading kind="dataset" />
      ) : error ? (
        <div className="blob-panel p-4 text-sm text-body">
          <p className="text-error font-medium">Could not load packages</p>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      ) : datasets.length === 0 ? (
        <CatalogEmpty
          kind="dataset"
          scope={scope}
          signedIn={Boolean(token)}
          searching={Boolean(query.trim())}
          onExplore={() => setScope("explore")}
          onClearSearch={() => setQuery("")}
        />
      ) : (
          <>
            <div className="blob-panel">
              <Table
                wrapClassName="overflow-visible"
                className="border-separate border-spacing-0"
              >
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={STICKY_TH}>
                      {sort.head("dataset", "Dataset")}
                    </TableHead>
                    <TableHead className={STICKY_TH}>
                      {sort.head("org", "Org")}
                    </TableHead>
                    <TableHead className={STICKY_TH}>
                      {sort.head("version", "Version")}
                    </TableHead>
                    <TableHead className={STICKY_TH}>
                      {sort.head("visibility", "Visibility")}
                    </TableHead>
                    <TableHead className={`${STICKY_TH} tabular-nums`}>
                      {sort.head("tasks", "Tasks")}
                    </TableHead>
                    {columns.includes("updated") ? (
                      <TableHead className={STICKY_TH}>
                        {sort.head("updated", "Updated")}
                      </TableHead>
                    ) : null}
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
                      <TableCell className="font-medium">
                        {packageDisplayTitle(row.dataset_id, row.display_name)}
                      </TableCell>
                      <TableCell className="text-mute">
                        {row.org_id ? (
                          <Link
                            to={`/organizations/${encodeURIComponent(row.org_id)}`}
                            className="text-link hover:text-link-deep"
                            onClick={(e) => e.stopPropagation()}
                          >
                            @{row.org_id}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-body">
                        {versionLabel(row)}
                      </TableCell>
                      <TableCell className="text-body">{row.visibility}</TableCell>
                      <TableCell className="tabular-nums text-body">
                        {typeof row.task_count === "number"
                          ? row.task_count.toLocaleString()
                          : "-"}
                      </TableCell>
                      {columns.includes("updated") ? (
                        <TableCell className="text-mute">
                          {typeof row.created_at === "number"
                            ? formatDate(
                                new Date(row.created_at * 1000).toISOString(),
                              )
                            : "-"}
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-xs text-mute mt-3 tabular-nums">
              {datasets.length} dataset{datasets.length === 1 ? "" : "s"}
            </p>
          </>
        )}
        </div>
      </div>
    </>
  );
}
