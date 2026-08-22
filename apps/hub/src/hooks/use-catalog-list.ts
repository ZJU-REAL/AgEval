import { useEffect, useState } from "react";

import {
  catalogListOpts,
  type CatalogScope,
} from "@/components/catalog-scope-bar";
import {
  catalogListCacheKey,
  hydrateCatalogRow,
  readCatalogList,
  writeCatalogList,
} from "@/lib/catalog-cache";
import {
  listPackages,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";

export function useCatalogList(
  kind: "plugin" | "agent",
  scope: CatalogScope,
  token: string | null,
  needsAuth: boolean,
): {
  items: PackageRelease[];
  error: string | null;
  loading: boolean;
} {
  const key = catalogListCacheKey(kind, scope, Boolean(token));
  const cached = needsAuth && !token ? [] : readCatalogList(key);
  const [live, setLive] = useState<{
    key: string;
    items: PackageRelease[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (needsAuth && !token) {
      setLive({ key, items: [] });
      setError(null);
      return;
    }
    let cancelled = false;
    listPackages(token, { packageKind: kind, ...catalogListOpts(scope) })
      .then((rows) => {
        const hydrated = rows.map(hydrateCatalogRow);
        writeCatalogList(key, hydrated);
        if (cancelled) return;
        setLive({ key, items: hydrated });
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (cached) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setLive({ key, items: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [key, kind, scope, token, needsAuth]);

  const items = live?.key === key ? live.items : (cached ?? []);
  const loading = live?.key !== key && cached == null && !(needsAuth && !token);
  return { items, error, loading };
}
