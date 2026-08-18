import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Job } from "@/lib/api";
import { jobDisplayName } from "@/lib/routes";

const NOTE_MAX = 2000;

type Props = {
  job: Job;
  initialNote: string;
  onClose: () => void;
  onSave: (note: string) => void;
};

export function JobNoteDialog({ job, initialNote, onClose, onSave }: Props) {
  const [text, setText] = useState(initialNote);
  const titleId = useId();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function submit() {
    onSave(text.trim());
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-lg rounded-[8px] border border-hairline bg-canvas shadow-[var(--viewer-shadow-pop)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-hairline px-4 py-3">
          <h2 id={titleId} className="text-sm font-medium text-ink">
            Note
          </h2>
          <p className="mt-1 text-xs text-mute font-mono truncate">
            {jobDisplayName(job)}
          </p>
        </div>
        <div className="px-4 py-3 space-y-2">
          <textarea
            autoFocus
            value={text}
            maxLength={NOTE_MAX}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Local note for this browser. Not written to evidence."
            className="min-h-[8rem] w-full resize-y rounded-[6px] border border-hairline bg-canvas px-3 py-2 text-sm text-ink placeholder:text-mute focus-visible:outline-none focus-visible:border-link"
            aria-label="Job note"
          />
          <p className="text-xs text-mute tabular">
            {text.length}/{NOTE_MAX} · stays in this browser
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-hairline px-4 py-3">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={submit}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
