import { Star } from "lucide-react";

import { cn, formatCount } from "@/lib/utils";

export function FavoriteCount({
  count,
  favorited = false,
  compact = false,
  className,
  onToggle,
}: {
  count?: number | null;
  favorited?: boolean;
  compact?: boolean;
  className?: string;
  onToggle?: () => void;
}) {
  const n =
    Number.isFinite(count) && (count as number) > 0 ? Math.floor(count as number) : 0;
  const label = n === 1 ? "1 favorite" : `${formatCount(n)} favorites`;
  const icon = (
    <Star
      className={compact ? "h-3 w-3" : "h-3.5 w-3.5"}
      strokeWidth={1.75}
      fill={favorited ? "currentColor" : "none"}
      aria-hidden
    />
  );
  const cls = cn(
    "inline-flex items-center gap-1 font-mono tabular-nums",
    favorited ? "text-ink" : "text-mute",
    compact ? "text-[11px]" : "text-xs",
    onToggle &&
      "rounded-[6px] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70",
    className,
  );
  if (onToggle) {
    return (
      <button
        type="button"
        className={cls}
        title={favorited ? "Remove favorite" : "Add favorite"}
        aria-label={favorited ? `Remove favorite (${label})` : `Add favorite (${label})`}
        aria-pressed={favorited}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onToggle();
        }}
        onKeyDown={(event) => event.stopPropagation()}
      >
        {icon}
        <span aria-hidden>{compact ? formatCount(n) : label}</span>
      </button>
    );
  }
  return (
    <span className={cls} title={label} aria-label={label}>
      {icon}
      <span aria-hidden>{compact ? formatCount(n) : label}</span>
    </span>
  );
}
