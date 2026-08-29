import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

import { ModelItem } from "@/components/model-item";
import { encodeDatasetId } from "@/lib/api";
import { loadModelPin } from "@/lib/model-pin";
import { cn } from "@/lib/utils";

const MAX_RESULTS = 50;

/** Cmd/Ctrl+F palette over the model pin: Enter opens /models/{canonical}. */
export function ModelSearchModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const pin = loadModelPin();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const rows = useMemo(() => {
    if (!open) return [];
    const q = query.trim().toLowerCase();
    const out: {
      canonical: string;
      info: (typeof pin.models)[string];
    }[] = [];
    for (const [canonical, info] of Object.entries(pin.models)) {
      const hay =
        `${canonical} ${info.name} ${info.family} ${info.lab} ${info.description}`.toLowerCase();
      if (q && !hay.includes(q)) continue;
      out.push({ canonical, info });
    }
    return out.slice(0, MAX_RESULTS);
  }, [open, query, pin]);

  const current = Math.min(active, Math.max(0, rows.length - 1));

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((a) => Math.min(a + 1, rows.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (event.key === "Enter") {
        const row = rows[Math.min(active, Math.max(0, rows.length - 1))];
        if (row) {
          onClose();
          navigate(`/models/${encodeDatasetId(row.canonical)}`);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, rows, active, onClose, navigate]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${current}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [current]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      data-ageval-scrim=""
      className="fixed inset-0 z-[70] flex items-center justify-center bg-ink/30 p-3 backdrop-blur-sm sm:p-6"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search models"
        data-ageval-pop=""
        className={cn(
          "flex w-[min(760px,100%)] flex-col overflow-hidden",
          "rounded-[14px] border border-hairline bg-canvas shadow-[var(--viewer-shadow-pop)]",
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-hairline px-4">
          <Search className="h-4 w-4 shrink-0 text-mute" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="Search models…"
            aria-label="Search models"
            autoComplete="off"
            spellCheck={false}
            className="h-12 min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-mute"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close search"
            className="shrink-0 rounded-[6px] border border-hairline px-1.5 py-0.5 text-xs text-mute transition-colors duration-200 ease-smooth hover:text-ink"
          >
            Esc
          </button>
        </div>
        <div
          ref={listRef}
          role="listbox"
          aria-label="Model results"
          className="max-h-[min(56vh,460px)] overflow-y-auto p-2"
        >
          <p className="px-2 pb-1.5 pt-1 text-xs font-medium uppercase tracking-[0.08em] text-mute">
            {rows.length} result{rows.length === 1 ? "" : "s"}
          </p>
          {rows.map((row, i) => (
            <ModelItem
              key={row.canonical}
              canonical={row.canonical}
              overlay={row.canonical}
              selected={i === current}
              title={row.info.description}
              role="option"
              aria-selected={i === current}
              data-index={i}
              onClick={() => {
                onClose();
                navigate(`/models/${encodeDatasetId(row.canonical)}`);
              }}
              onMouseEnter={() => setActive(i)}
            />
          ))}
          {rows.length === 0 ? (
            <p className="px-3 py-6 text-sm text-mute">No models match</p>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
