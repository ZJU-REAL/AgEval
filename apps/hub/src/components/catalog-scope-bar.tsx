import { UnderlineTabs } from "@/components/underline-tabs";
import { Input } from "@/components/ui/input";

export type CatalogScope = "orgs" | "explore" | "favorites";

export const DATASET_SCOPE_ITEMS = [
  { id: "orgs" as const, label: "Your organizations" },
  { id: "explore" as const, label: "Explore" },
];

export const MARKETPLACE_SCOPE_ITEMS = [
  ...DATASET_SCOPE_ITEMS,
  { id: "favorites" as const, label: "Stars" },
];

function truthyParam(raw: string | null): boolean {
  const v = (raw || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes";
}

/** Hub list URL is the list filter: default orgs, `visibility=public`, `favorited=1`. */
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
  if (params.get("visibility") === "public" || params.get("scope") === "explore") {
    return "explore";
  }
  return "orgs";
}

export function catalogScopeSearch(scope: CatalogScope): Record<string, string> {
  if (scope === "favorites") return { favorited: "1" };
  if (scope === "explore") return { visibility: "public" };
  return {};
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
}: {
  scope: T;
  onScope: (next: T) => void;
  items: readonly { id: T; label: string }[];
  query: string;
  onQuery: (next: string) => void;
  searchLabel: string;
  searchPlaceholder: string;
}) {
  return (
    <div className="mb-4">
      <UnderlineTabs
        items={items}
        value={scope}
        onChange={onScope}
        ariaLabel="Catalog scope"
      />
      <div className="pt-3">
        <Input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchLabel}
          className="w-full max-w-sm focus-visible:border-hairline"
        />
      </div>
    </div>
  );
}
