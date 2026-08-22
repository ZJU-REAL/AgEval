import { useMemo, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import {
  BrandMarkPicker,
  type MarkDraft,
} from "@/components/brand-mark-picker";
import { toast } from "@/components/ui/toast";
import { updatePackageIcon } from "@/lib/api";
import {
  resolveEntityMark,
  type EntityMarkHint,
} from "@/lib/brand-marks";
import { cn } from "@/lib/utils";

function draftFromHint(hint: EntityMarkHint): MarkDraft {
  const key = (hint.iconKey || "").trim();
  if (key) return { mode: "catalog", id: key };
  const github = (hint.iconGithub || "").trim();
  if (github) return { mode: "github", login: github };
  return { mode: "default" };
}

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
  onUpdated: (patch: { icon_key?: string; icon_github?: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mark = useMemo(() => resolveEntityMark(hint), [hint]);

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
        current={draftFromHint(hint)}
        uploadedBy={hint.uploadedBy}
        busy={busy}
        error={error}
        onCancel={() => {
          if (!busy) setOpen(false);
        }}
        onSave={(draft) => {
          const body =
            draft.mode === "catalog"
              ? { icon_key: draft.id, icon_github: "" }
              : draft.mode === "github"
                ? { icon_key: "", icon_github: draft.login }
                : { icon_key: "", icon_github: "" };
          setBusy(true);
          setError(null);
          void updatePackageIcon(packageId, body, token)
            .then((updated) => {
              onUpdated({
                icon_key: updated.icon_key || "",
                icon_github: updated.icon_github || "",
              });
              setOpen(false);
              toast("Icon updated");
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
