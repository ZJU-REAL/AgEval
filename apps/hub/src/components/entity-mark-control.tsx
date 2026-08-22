import { useMemo, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { BrandMarkPicker } from "@/components/brand-mark-picker";
import { updatePackageIconKey } from "@/lib/api";
import {
  resolveEntityMark,
  type EntityMarkHint,
} from "@/lib/brand-marks";
import { cn } from "@/lib/utils";

export function EntityMarkControl({
  hint,
  packageId,
  token,
  canEdit,
  size = 28,
  onUpdated,
}: {
  hint: EntityMarkHint;
  packageId: string;
  token: string | null;
  canEdit: boolean;
  size?: number;
  onUpdated: (iconKey: string | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mark = useMemo(() => resolveEntityMark(hint), [hint]);
  const stored = (hint.iconKey || "").trim();

  if (!canEdit) {
    return <BrandMark mark={mark} size={size} />;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
        aria-label="Change icon"
        className={cn(
          "inline-flex shrink-0 rounded-[6px] p-0.5",
          "hover:bg-canvas-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70",
        )}
      >
        <BrandMark mark={mark} size={size} />
      </button>
      <BrandMarkPicker
        open={open}
        currentKey={stored || null}
        busy={busy}
        error={error}
        onCancel={() => {
          if (!busy) setOpen(false);
        }}
        onSave={(iconKey) => {
          setBusy(true);
          setError(null);
          void updatePackageIconKey(packageId, iconKey, token)
            .then((updated) => {
              onUpdated(updated.icon_key || undefined);
              setOpen(false);
            })
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : String(err));
            })
            .finally(() => setBusy(false));
        }}
      />
    </>
  );
}
