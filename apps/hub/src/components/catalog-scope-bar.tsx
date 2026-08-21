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
    <div className="mb-4">
      <div className="flex gap-1 border-b border-hairline">
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
