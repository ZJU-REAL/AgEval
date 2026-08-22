import { Puzzle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { CatalogCardGrid, CatalogCardSkeleton } from "@/components/catalog-card";
import {
  CatalogScopeBar,
  MARKETPLACE_SCOPE_ITEMS,
  type CatalogScope,
} from "@/components/catalog-scope-bar";
import { PageHead } from "@/components/page-head";
import { SignInLink } from "@/components/sign-in-button";
import {
  encodeDatasetId,
  latestPackageByDataset,
  listOrgs,
  listPackages,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

function parseScope(raw: string | null): CatalogScope {
  if (raw === "explore" || raw === "favorites") return raw;
  return "orgs";
}

export function PluginsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const scope = parseScope(searchParams.get("scope"));

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
    const latest = latestPackageByDataset(items);
    const scoped =
      scope === "orgs"
        ? latest.filter((r) => r.org_id && myOrgIds.has(r.org_id) && token)
        : scope === "favorites"
          ? latest.filter((r) => r.favorited && token)
          : latest.filter((r) => r.visibility === "public");
    const q = query.trim().toLowerCase();
    if (!q) return scoped;
    return scoped.filter(
      (r) =>
        r.dataset_id.toLowerCase().includes(q) ||
        (r.org_id && r.org_id.toLowerCase().includes(q)),
    );
  }, [items, scope, myOrgIds, query, token]);

  function setScope(next: CatalogScope) {
    setSearchParams(next === "orgs" ? {} : { scope: next }, { replace: true });
  }

  function patchFavorite(
    id: string,
    next: { favorited: boolean; favorite_count: number },
  ) {
    setItems((prev) =>
      prev.map((row) =>
        row.dataset_id === id
          ? { ...row, favorited: next.favorited, favorite_count: next.favorite_count }
          : row,
      ),
    );
  }

  function openPlugin(id: string) {
    navigate(`/plugins/${encodeDatasetId(id)}`);
  }

  return (
    <>
      <PageHead
        title="Plugin marketplace"
        sub={
          <>
            Browse <span className="font-mono text-xs">ageval.plugin/1</span>{" "}
            packages. Install is CLI-only (Recognition only — does not change
            profiles).
          </>
        }
      />

      <CatalogScopeBar
        scope={scope}
        onScope={setScope}
        items={MARKETPLACE_SCOPE_ITEMS}
        query={query}
        onQuery={setQuery}
        searchLabel="Search plugins"
        searchPlaceholder="Search plugins…"
      />

      {(scope === "orgs" || scope === "favorites") && !token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">
            {scope === "favorites"
              ? "Sign in to see favorite plugins"
              : "Sign in to see org plugins"}
          </p>
          <p className="mt-1 text-mute">
            <SignInLink /> to list{" "}
            {scope === "favorites"
              ? "plugins you favorited"
              : "plugins from your organizations"}
            . Public plugins are under{" "}
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
        <CatalogCardSkeleton />
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
                  ? "No plugin packages from your organizations yet. Publish with ageval plugin publish <path> --org <id>."
                  : scope === "favorites"
                    ? "No favorite plugins yet. Star a plugin from Explore."
                    : "No public plugin packages on this Registry yet."}
              </p>
            </div>
          ) : (
            <CatalogCardGrid
              kind="plugin"
              rows={plugins}
              onOpen={openPlugin}
              onFavoriteChange={patchFavorite}
            />
          )}
          <p className="text-xs text-mute mt-3 tabular-nums">
            {plugins.length} plugin{plugins.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
