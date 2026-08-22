import { DownloadCount } from "@/components/download-count";
import { FavoriteCount } from "@/components/favorite-count";
import { cn } from "@/lib/utils";

export function MarketplaceCounts({
  downloadCount,
  favoriteCount,
  favorited = false,
  compact = false,
  className,
  onToggleFavorite,
}: {
  downloadCount?: number | null;
  favoriteCount?: number | null;
  favorited?: boolean;
  compact?: boolean;
  className?: string;
  onToggleFavorite?: () => void;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <DownloadCount count={downloadCount} compact={compact} />
      <FavoriteCount
        count={favoriteCount}
        favorited={favorited}
        compact={compact}
        onToggle={onToggleFavorite}
      />
    </span>
  );
}
