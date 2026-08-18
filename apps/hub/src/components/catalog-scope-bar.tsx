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
    <div className="flex items-end gap-3 border-b border-hairline mb-4">
      <div className="flex gap-1 min-w-0 shrink-0">
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
              "px-3 py-2 font-mono text-xs uppercase tracking-wide transition-colors border-b-2 -mb-px",
              scope === id
                ? "border-link text-ink font-semibold"
                : "border-transparent text-mute hover:text-body",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="ml-auto w-40 sm:w-64 shrink-0 pb-1.5">
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
