import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

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
  listPackages,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

/** Collapse multi-version list to latest per database_id (by created_at). */
function latestByDatabase(items: PackageRelease[]): PackageRelease[] {
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

export function DatasetsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<PackageRelease[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const token = getToken();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listPackages(token)
      .then((rows) => {
        if (!cancelled) {
          setItems(rows);
          setError(null);
        }
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

  const datasets = useMemo(() => latestByDatabase(items), [items]);

  function openDataset(id: string) {
    navigate(`/datasets/${encodeDatasetId(id)}`);
  }

  return (
    <Shell>
      <BreadcrumbNav items={[{ label: "Datasets" }]} className="mb-4" />
      <div className="flex items-baseline justify-between gap-4 mb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">Datasets</h1>
          <p className="text-sm text-body mt-1">
            Public Registry packages
            {token ? " (including private visible to your token)" : ""}.
            Sign in to see authorized private Datasets.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm text-body">
          <p className="text-error font-medium">Could not load packages</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
          <p className="mt-2 text-mute">
            Ensure Registry is running and{" "}
            <code className="font-mono">VITE_REGISTRY_PROXY_TARGET</code> points at it.
          </p>
        </div>
      ) : datasets.length === 0 ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">No Datasets yet</p>
          <p className="mt-1 text-mute">
            Publish with <code className="font-mono">bora publish</code> (public) or sign in
            for private.
          </p>
        </div>
      ) : (
        <div className="rounded-[8px] border border-hairline overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Dataset</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Visibility</TableHead>
                <TableHead className="text-right tabular-nums">Size</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {datasets.map((row) => (
                <TableRow
                  key={`${row.database_id}@${row.version}`}
                  className="cursor-pointer"
                  onClick={() => openDataset(row.database_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openDataset(row.database_id);
                    }
                  }}
                  tabIndex={0}
                  role="link"
                >
                  <TableCell className="font-medium font-mono text-sm">
                    {row.database_id}
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
                      ? formatDate(new Date(row.created_at * 1000).toISOString())
                      : "-"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Shell>
  );
}
