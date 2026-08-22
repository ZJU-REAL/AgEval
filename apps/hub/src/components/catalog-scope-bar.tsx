import { UnderlineTabs } from "@/components/underline-tabs";
import { Input } from "@/components/ui/input";

export type CatalogScope = "orgs" | "explore" | "favorites";

export const DATASET_SCOPE_ITEMS = [
  { id: "orgs" as const, label: "Your organizations" },
  { id: "explore" as const, label: "Explore" },
];

export const MARKETPLACE_SCOPE_ITEMS = [
  ...DATASET_SCOPE_ITEMS,
  { id: "favorites" as const, label: "Favorites" },
];

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
          className="w-full max-w-sm"
        />
      </div>
    </div>
  );
}
