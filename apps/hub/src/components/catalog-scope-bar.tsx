import { UnderlineTabs } from "@/components/underline-tabs";
import { Input } from "@/components/ui/input";

type Scope = "orgs" | "explore";

const SCOPE_ITEMS = [
  { id: "orgs" as const, label: "Your organizations" },
  { id: "explore" as const, label: "Explore" },
];

export function CatalogScopeBar({
  scope,
  onScope,
  query,
  onQuery,
  searchLabel,
  searchPlaceholder,
}: {
  scope: Scope;
  onScope: (next: Scope) => void;
  query: string;
  onQuery: (next: string) => void;
  searchLabel: string;
  searchPlaceholder: string;
}) {
  return (
    <div className="mb-4">
      <UnderlineTabs
        items={SCOPE_ITEMS}
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
