import { useEffect, useMemo, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { BRAND_MARKS } from "@/lib/brand-marks";
import { cn } from "@/lib/utils";

export function BrandMarkPicker({
  open,
  currentKey,
  busy = false,
  error = null,
  onCancel,
  onSave,
}: {
  open: boolean;
  currentKey: string | null;
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onSave: (iconKey: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string>(currentKey || "");

  useEffect(() => {
    if (!open) return;
    setSelected(currentKey || "");
    setQuery("");
  }, [open, currentKey]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return BRAND_MARKS;
    return BRAND_MARKS.filter((row) => {
      if (row.id.includes(q) || row.label.toLowerCase().includes(q)) return true;
      return row.aliases.some((alias) => alias.includes(q));
    });
  }, [query]);

  return (
    <ConfirmDialog
      open={open}
      title="Choose icon"
      description="Closed catalog only. Default uses the name alias, or a letter if nothing matches."
      confirmLabel="Save"
      confirmVariant="default"
      busy={busy}
      error={error}
      className="max-w-lg"
      onCancel={onCancel}
      onConfirm={() => onSave(selected)}
    >
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search"
        aria-label="Search icons"
        className="mb-3"
        autoFocus
      />
      <div className="grid max-h-72 grid-cols-4 gap-1.5 overflow-auto sm:grid-cols-5">
        <button
          type="button"
          onClick={() => setSelected("")}
          className={cn(
            "flex flex-col items-center gap-1 rounded-[8px] border px-2 py-2 text-center",
            selected === ""
              ? "border-link bg-canvas-soft"
              : "border-hairline hover:bg-canvas-soft",
          )}
        >
          <BrandMark mark={{ key: null, letter: "?" }} size={20} />
          <span className="font-mono text-[10px] text-mute">Default</span>
        </button>
        {rows.map((row) => (
          <button
            type="button"
            key={row.id}
            onClick={() => setSelected(row.id)}
            className={cn(
              "flex flex-col items-center gap-1 rounded-[8px] border px-2 py-2 text-center",
              selected === row.id
                ? "border-link bg-canvas-soft"
                : "border-hairline hover:bg-canvas-soft",
            )}
          >
            <BrandMark mark={{ key: row.id, letter: row.label[0] || "?" }} size={20} />
            <span className="w-full truncate font-mono text-[10px] text-body">
              {row.label}
            </span>
          </button>
        ))}
      </div>
    </ConfirmDialog>
  );
}
