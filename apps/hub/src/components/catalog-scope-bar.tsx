import type { ReactNode } from "react";

import { UnderlineTabs } from "@/components/underline-tabs";
import { Input } from "@/components/ui/input";

export type CatalogScope = "orgs" | "explore" | "favorites";

export const DATASET_SCOPE_ITEMS = [
  { id: "explore" as const, label: "Explore" },
  { id: "orgs" as const, label: "Your organizations" },
];

export const MARKETPLACE_SCOPE_ITEMS = [
  ...DATASET_SCOPE_ITEMS,
  { id: "favorites" as const, label: "Stars" },
];

function truthyParam(raw: string | null): boolean {
  const v = (raw || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes";
}

/** Hub list URL is the list filter: default Explore (`visibility=public`), `orgs=1`, `favorited=1`. */
export function catalogScopeFromSearch(
  params: URLSearchParams,
  allowFavorites = true,
): CatalogScope {
  if (
    allowFavorites &&
    (truthyParam(params.get("favorited")) || params.get("scope") === "favorites")
  ) {
    return "favorites";
  }
  if (params.get("orgs") === "1" || params.get("scope") === "orgs") {
    return "orgs";
  }
  return "explore";
}

export function catalogScopeSearch(scope: CatalogScope): Record<string, string> {
  if (scope === "favorites") return { favorited: "1" };
  if (scope === "orgs") return { orgs: "1" };
  return { visibility: "public" };
}

export function catalogListOpts(scope: CatalogScope): {
  orgs?: boolean;
  visibility?: "public";
  favorited?: boolean;
} {
  if (scope === "favorites") return { favorited: true };
  if (scope === "explore") return { visibility: "public" };
  return { orgs: true };
}

export function CatalogScopeBar<T extends string>({
  scope,
  onScope,
  items,
  query,
  onQuery,
  searchLabel,
  searchPlaceholder,
  end,
}: {
  scope: T;
  onScope: (next: T) => void;
  items: readonly { id: T; label: string }[];
  query: string;
  onQuery: (next: string) => void;
  searchLabel: string;
  searchPlaceholder: string;
  /** Trailing chrome on the search row. */
  end?: ReactNode;
}) {
  return (
    <div className="mb-4">
      <UnderlineTabs
        items={items}
        value={scope}
        onChange={onScope}
        ariaLabel="Catalog scope"
      />
      <div className="flex items-center gap-2 pt-3">
        <Input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchLabel}
          className="min-w-0 w-full max-w-sm"
        />
        {end ? <div className="ml-auto shrink-0">{end}</div> : null}
      </div>
    </div>
  );
}
