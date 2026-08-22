import { Bot } from "lucide-react";
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

export function AgentsPage() {
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
    const packagesP = listPackages(token, { packageKind: "agent" });
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

  const agents = useMemo(() => {
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

  function openAgent(id: string) {
    navigate(`/agents/${encodeDatasetId(id)}`);
  }

  return (
    <>
      <PageHead
        title="Agent hub"
        sub={
          <>
            Browse <span className="font-mono text-xs">ageval.agent/1</span>{" "}
            definitions (one job binding: executor × model × options). Install
            is CLI-only and never edits profiles; bind at run time with{" "}
            <span className="font-mono text-xs">--agent</span>.
          </>
        }
      />

      <CatalogScopeBar
        scope={scope}
        onScope={setScope}
        items={MARKETPLACE_SCOPE_ITEMS}
        query={query}
        onQuery={setQuery}
        searchLabel="Search agents"
        searchPlaceholder="Search agents…"
      />

      {(scope === "orgs" || scope === "favorites") && !token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">
            {scope === "favorites"
              ? "Sign in to see favorite agents"
              : "Sign in to see org agents"}
          </p>
          <p className="mt-1 text-mute">
            <SignInLink /> to list{" "}
            {scope === "favorites"
              ? "agents you favorited"
              : "agents from your organizations"}
            . Public agents are under{" "}
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
          <p className="text-error font-medium">Could not load agents</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
        </div>
      ) : (
        <>
          {agents.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm text-body">
              <div className="flex justify-center mb-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
                  <Bot className="h-8 w-8" strokeWidth={1.5} aria-hidden />
                </div>
              </div>
              <p className="font-medium text-ink">No agents found</p>
              <p className="mt-1 text-mute max-w-md mx-auto">
                {scope === "orgs"
                  ? "No agent packages from your organizations yet. Publish with ageval agent publish <path> --org <id>."
                  : scope === "favorites"
                    ? "No favorite agents yet. Star an agent from Explore."
                    : "No public agent packages on this Registry yet."}
              </p>
            </div>
          ) : (
            <CatalogCardGrid
              kind="agent"
              rows={agents}
              onOpen={openAgent}
              onFavoriteChange={patchFavorite}
            />
          )}
          <p className="text-xs text-mute mt-3 tabular-nums">
            {agents.length} agent{agents.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
