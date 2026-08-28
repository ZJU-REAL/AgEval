import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Boxes } from "lucide-react";

import { CatalogScopeBar } from "@/components/catalog-scope-bar";
import { EmptyState, LoadingState } from "@/components/empty-state";
import { MODALITY_TAB_META } from "@/components/modality-mark";
import { ModelDirectory, type ModelDirectoryRow } from "@/components/model-directory";
import { PageHead } from "@/components/page-head";
import { UnderlineTabs } from "@/components/underline-tabs";
import { encodeDatasetId } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  appearancesByCanonical,
  collectModelAppearances,
} from "@/lib/model-appearances";
import {
  loadModelPin,
  matchesModalityTab,
  modalityTabFromSearch,
  modelModalities,
  type ModalityTab,
} from "@/lib/model-pin";

type ModelScope = "explore" | "performance";

const SCOPE_ITEMS = [
  { id: "explore" as const, label: "Explore" },
  { id: "performance" as const, label: "Has Performance" },
];

function scopeFromSearch(params: URLSearchParams): ModelScope {
  return params.get("performance") === "1" ? "performance" : "explore";
}

export function ModelsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const scope = scopeFromSearch(searchParams);
  const modality = modalityTabFromSearch(searchParams.get("mod"));
  const [query, setQuery] = useState("");
  const token = getToken();
  const pin = loadModelPin();
  const [perfCanonicals, setPerfCanonicals] = useState<Set<string> | null>(null);
  const [loadingPerf, setLoadingPerf] = useState(false);

  function writeFilters(nextScope: ModelScope, nextMod: ModalityTab) {
    const next: Record<string, string> = {};
    if (nextScope === "performance") next.performance = "1";
    if (nextMod !== "all") next.mod = nextMod;
    setSearchParams(next, { replace: true });
  }

  useEffect(() => {
    if (scope !== "performance") return;
    let cancelled = false;
    setLoadingPerf(true);
    void collectModelAppearances(token)
      .then((rows) => {
        if (cancelled) return;
        setPerfCanonicals(new Set(appearancesByCanonical(rows).keys()));
      })
      .catch(() => {
        if (!cancelled) setPerfCanonicals(new Set());
      })
      .finally(() => {
        if (!cancelled) setLoadingPerf(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scope, token]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: ModelDirectoryRow[] = [];
    for (const [canonical, info] of Object.entries(pin.models)) {
      if (scope === "performance" && !perfCanonicals?.has(canonical)) continue;
      if (!matchesModalityTab(modelModalities(info), modality)) continue;
      const hay = `${canonical} ${info.name} ${info.family} ${info.lab}`.toLowerCase();
      if (q && !hay.includes(q)) continue;
      out.push({
        overlay: canonical,
        canonical,
        href: `/models/${encodeDatasetId(canonical)}`,
      });
    }
    return out;
  }, [pin.models, query, scope, modality, perfCanonicals]);

  function setScope(next: ModelScope) {
    writeFilters(next, modality);
  }

  const emptyPin = Object.keys(pin.models).length === 0;
  const waiting = scope === "performance" && (loadingPerf || perfCanonicals === null);

  return (
    <>
      <PageHead
        title="Models"
        sub="Pinned encyclopedia. Overlay invoke ids stay as run; Hub joins a unique canonical when it can."
      />
      <CatalogScopeBar
        scope={scope}
        onScope={setScope}
        items={SCOPE_ITEMS}
        query={query}
        onQuery={setQuery}
        searchLabel="Search models"
        searchPlaceholder="Search models…"
      />
      <UnderlineTabs
        className="mb-4"
        ariaLabel="Model modalities"
        items={MODALITY_TAB_META}
        value={modality}
        onChange={(next) => writeFilters(scope, next)}
      />
      {emptyPin ? (
        <EmptyState
          icon={Boxes}
          glyph="models"
          title="No model pin"
          caption="Letter marks only until a maintainer syncs the snapshot."
        />
      ) : waiting ? (
        <LoadingState label="Loading models" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Boxes}
          glyph="models"
          title={
            query.trim() || modality !== "all" ? "No models match" : "No models with Performance"
          }
          caption={
            query.trim() || modality !== "all"
              ? undefined
              : "Plaza collect and consented attach fill this filter."
          }
          action={
            query.trim() ? (
              <button
                type="button"
                className="text-sm text-link hover:text-link-deep"
                onClick={() => setQuery("")}
              >
                Clear search
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <ModelDirectory rows={rows} showOverlay={false} />
          <p className="mt-3 text-xs text-mute tabular-nums">
            {rows.length} model{rows.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
