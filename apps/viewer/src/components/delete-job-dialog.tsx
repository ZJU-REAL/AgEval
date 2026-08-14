import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  deleteJob,
  fetchDeletePreview,
  type DeletePreview,
  type Job,
} from "@/lib/api";
import { jobDisplayName } from "@/lib/routes";
import { formatBytes } from "@/lib/utils";

type Props = {
  job: Job;
  onClose: () => void;
  onDeleted: () => void;
};

export function DeleteJobDialog({ job, onClose, onDeleted }: Props) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDeletePreview(job.job_id)
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
        setError(null);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job.job_id]);

  async function onConfirm() {
    if (!preview?.can_delete || !preview.confirm_token) return;
    setBusy(true);
    try {
      await deleteJob(job.job_id, preview.confirm_token);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const kind = preview?.kind || job.source_kind || "job";
  const refuse = preview?.error?.message || error;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-job-title"
        className="w-full max-w-lg rounded-[8px] border border-hairline bg-canvas shadow-[0_8px_24px_-8px_#00000024]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-hairline px-4 py-3">
          <h2 id="delete-job-title" className="text-sm font-medium text-ink">
            Delete {kind} job
          </h2>
          <p className="mt-1 text-xs text-mute font-mono truncate">
            {jobDisplayName(job)}
          </p>
        </div>
        <div className="px-4 py-3 space-y-3 text-sm">
          {kind === "suite" ? (
            <p className="text-body">
              This removes the suite tree and every Attempt it references. Those
              Attempts will not come back as singles.
            </p>
          ) : (
            <p className="text-body">This removes this Attempt directory.</p>
          )}
          {loading && <p className="text-mute">Loading preview...</p>}
          {refuse && <p className="text-error">{refuse}</p>}
          {preview && (
            <>
              <ul className="max-h-48 overflow-auto rounded-[6px] border border-hairline bg-canvas-soft divide-y divide-hairline">
                {preview.paths.map((row) => (
                  <li
                    key={row.locator}
                    className="flex items-start justify-between gap-3 px-2.5 py-1.5"
                  >
                    <span className="font-mono text-xs break-all">
                      {row.locator}
                      {!row.exists ? (
                        <span className="text-mute"> (missing)</span>
                      ) : null}
                    </span>
                    <span className="tabular text-xs text-mute shrink-0">
                      {formatBytes(row.bytes)}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-mute tabular">
                {formatBytes(preview.bytes)} total
                {preview.cascade_run_ids.length
                  ? ` · ${preview.cascade_run_ids.length} attempt${
                      preview.cascade_run_ids.length === 1 ? "" : "s"
                    }`
                  : ""}
              </p>
            </>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-hairline px-4 py-3">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => void onConfirm()}
            disabled={busy || loading || !preview?.can_delete}
          >
            {busy ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}
