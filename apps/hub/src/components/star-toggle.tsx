import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Star } from "lucide-react";

import { setPackageFavorite, type PackageRelease } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { rememberReturnPath } from "@/lib/return-path";
import { cn } from "@/lib/utils";

export function StarToggle({
  starred,
  busy = false,
  onToggle,
}: {
  starred: boolean;
  busy?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={starred}
      aria-label={starred ? "Unstar" : "Star"}
      title={starred ? "Unstar" : "Star"}
      onClick={onToggle}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-[6px]",
        "transition-colors duration-200 ease-smooth",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70",
        "disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]",
        starred ? "text-star" : "text-mute hover:text-body",
      )}
    >
      <Star
        className="h-4 w-4"
        strokeWidth={1.75}
        fill={starred ? "currentColor" : "none"}
        aria-hidden
      />
    </button>
  );
}

export function PackageStarButton({
  packageId,
  release,
  onUpdated,
}: {
  packageId: string;
  release: PackageRelease;
  onUpdated: (next: { favorited: boolean; favorite_count: number }) => void;
}) {
  const navigate = useNavigate();
  const token = getToken();
  const [busy, setBusy] = useState(false);
  return (
    <StarToggle
      starred={Boolean(release.favorited)}
      busy={busy}
      onToggle={() => {
        if (!token) {
          rememberReturnPath(window.location.pathname + window.location.search);
          navigate("/login");
          return;
        }
        setBusy(true);
        void setPackageFavorite(packageId, !release.favorited, token)
          .then(onUpdated)
          .finally(() => setBusy(false));
      }}
    />
  );
}
