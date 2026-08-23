import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmVariant = "danger",
  busy = false,
  confirmDisabled = false,
  error = null,
  children,
  className,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "danger" | "default";
  busy?: boolean;
  confirmDisabled?: boolean;
  error?: string | null;
  children?: ReactNode;
  className?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      data-ageval-scrim=""
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
      role="presentation"
      onClick={() => {
        if (!busy) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-desc"
        data-ageval-pop=""
        className={cn(
          "w-full max-w-md rounded-[12px] border border-hairline bg-canvas p-5 shadow-[var(--viewer-shadow-pop)]",
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="text-lg font-semibold tracking-tight text-ink"
        >
          {title}
        </h2>
        <div id="confirm-dialog-desc" className="mt-1 text-sm text-mute">
          {description}
        </div>
        {children ? <div className="mt-4">{children}</div> : null}
        {error ? (
          <p className="mt-3 text-sm font-mono text-error">{error}</p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={confirmVariant}
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {busy ? "…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Content modal (share / settings). Close is the only chrome action. */
export function Modal({
  open,
  title,
  description,
  children,
  error = null,
  className,
  onClose,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  error?: string | null;
  className?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      data-ageval-scrim=""
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="panel-dialog-title"
        aria-describedby={description ? "panel-dialog-desc" : undefined}
        data-ageval-pop=""
        className={cn(
          "w-full max-w-lg rounded-[12px] border border-hairline bg-canvas p-5 shadow-[var(--viewer-shadow-pop)]",
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <h2
            id="panel-dialog-title"
            className="min-w-0 flex-1 text-lg font-semibold tracking-tight text-ink"
          >
            {title}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close"
            className="-mr-1 -mt-1 h-8 w-8 text-mute"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>
        {description ? (
          <div id="panel-dialog-desc" className="mt-1 text-sm text-mute">
            {description}
          </div>
        ) : null}
        {children ? <div className="mt-4">{children}</div> : null}
        {error ? (
          <p className="mt-3 text-sm font-mono text-error">{error}</p>
        ) : null}
      </div>
    </div>
  );
}
