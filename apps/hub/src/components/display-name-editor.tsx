import { Check, Pencil, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { HoverTip } from "@/components/hover-tip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function DisplayNameEditor({
  value,
  canEdit,
  headingClassName,
  prefix,
  afterTitle,
  onSave,
}: {
  value: string;
  canEdit: boolean;
  headingClassName?: string;
  /** Locked ``org/`` prefix for plugin ids. Saved value is the leaf only. */
  prefix?: string | null;
  afterTitle?: ReactNode;
  onSave: (next: string) => Promise<void>;
}) {
  const locked = (prefix || "").trim();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  const title = locked ? `${locked}${value}` : value;

  async function submit() {
    const next = draft.trim();
    if (!next || next === value) {
      setEditing(false);
      setError(null);
      return;
    }
    if (next.includes("/")) {
      setError("Edit only the name after the org prefix");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(next);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <form
        className="flex flex-col gap-1 min-w-0"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="flex items-center gap-1.5">
          {locked ? (
            <span className="font-mono text-sm text-mute shrink-0">{locked}</span>
          ) : null}
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Display name"
            maxLength={80}
            autoFocus
            disabled={busy}
            className="h-8 w-36 shrink-0"
          />
          <Button
            type="submit"
            size="icon"
            variant="secondary"
            disabled={busy}
            aria-label="Save"
            className="h-8 w-8 shrink-0"
          >
            <Check className="size-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            disabled={busy}
            aria-label="Cancel"
            className="h-8 w-8 shrink-0"
            onClick={() => {
              setDraft(value);
              setEditing(false);
              setError(null);
            }}
          >
            <X className="size-4" />
          </Button>
        </div>
        {error ? <p className="text-xs text-error">{error}</p> : null}
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 min-w-0">
      <h1 className={cn("min-w-0 truncate", headingClassName)}>{title}</h1>
      {afterTitle}
      {canEdit ? (
        <HoverTip content="Edit display name">
          <button
            type="button"
            className="inline-flex shrink-0 rounded-[6px] p-1 text-mute hover:text-body hover:bg-canvas-soft"
            aria-label="Edit display name"
            onClick={() => setEditing(true)}
          >
            <Pencil className="size-4" strokeWidth={1.75} />
          </button>
        </HoverTip>
      ) : null}
    </div>
  );
}
