import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Scope = "orgs" | "explore";

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
    <div className="flex flex-wrap items-end gap-3 border-b border-hairline mb-4">
      <div className="flex gap-1 min-w-0">
        {(
          [
            ["orgs", "Your organizations"],
            ["explore", "Explore"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => onScope(id)}
            className={cn(
              "px-3 py-2 text-sm transition-colors border-b-2 -mb-px",
              scope === id
                ? "border-ink text-ink font-medium"
                : "border-transparent text-body hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="ml-auto w-full sm:w-64 pb-2 sm:pb-1.5">
        <Input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchLabel}
        />
      </div>
    </div>
  );
}
