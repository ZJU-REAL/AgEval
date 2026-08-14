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

type PreviewRow = {
  job: Job;
  preview: DeletePreview | null;
  error: string | null;
};

type Props = {
  jobs: Job[];
  onClose: () => void;
  onDeleted: (jobIds: string[]) => void;
};

export function DeleteJobDialog({ jobs, onClose, onDeleted }: Props) {
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const ids = jobs.map((j) => j.job_id).join(",");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all(
      jobs.map(async (job) => {
        try {
          const preview = await fetchDeletePreview(job.job_id);
          return { job, preview, error: preview.can_delete ? null : preview.error?.message || "cannot delete" };
        } catch (e) {
          return {
            job,
            preview: null,
            error: e instanceof Error ? e.message : String(e),
          };
        }
      }),
    )
      .then((next) => {
        if (!cancelled) {
          setRows(next);
          setError(null);
        }
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
  }, [ids, jobs]);

  const ready = rows.filter((r) => r.preview?.can_delete && r.preview.confirm_token);
  const blocked = rows.filter((r) => r.error);
  const paths = ready.flatMap((r) => r.preview?.paths || []);
  const bytes = ready.reduce((sum, r) => sum + (r.preview?.bytes || 0), 0);
  const cascade = ready.reduce((sum, r) => sum + (r.preview?.cascade_run_ids.length || 0), 0);
  const bulk = jobs.length > 1;
  const singleKind = rows[0]?.preview?.kind || jobs[0]?.source_kind || "job";

  async function onConfirm() {
    if (ready.length === 0) return;
    setBusy(true);
    const deleted: string[] = [];
    const failures: string[] = [];
    for (const row of ready) {
      const token = row.preview?.confirm_token;
      if (!token) continue;
      try {
        await deleteJob(row.job.job_id, token);
        deleted.push(row.job.job_id);
      } catch (e) {
        failures.push(
          `${jobDisplayName(row.job)}: ${e instanceof Error ? e.message : String(e)}`,
        );
      }
    }
    if (deleted.length && !failures.length) {
      onDeleted(deleted);
      return;
    }
    if (deleted.length) onDeleted(deleted);
    setError(failures.join(" · ") || "nothing can be deleted");
    setBusy(false);
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
        aria-labelledby="delete-job-title"
        className="w-full max-w-lg rounded-[8px] border border-hairline bg-canvas shadow-[0_8px_24px_-8px_#00000024]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-hairline px-4 py-3">
          <h2 id="delete-job-title" className="text-sm font-medium text-ink">
            {bulk ? `Delete ${jobs.length} jobs` : `Delete ${singleKind} job`}
          </h2>
          <p className="mt-1 text-xs text-mute font-mono truncate">
            {bulk
              ? jobs.map((j) => jobDisplayName(j)).join(", ")
              : jobDisplayName(jobs[0])}
          </p>
        </div>
        <div className="px-4 py-3 space-y-3 text-sm">
          {bulk ? (
            <p className="text-body">
              This removes each selected Job. Suite rows also delete every
              Attempt they reference.
            </p>
          ) : singleKind === "suite" ? (
            <p className="text-body">
              This removes the suite tree and every Attempt it references. Those
              Attempts will not come back as singles.
            </p>
          ) : (
            <p className="text-body">This removes this Attempt directory.</p>
          )}
          {loading && <p className="text-mute">Loading preview...</p>}
          {error ? <p className="text-error">{error}</p> : null}
          {blocked.map((row) => (
            <p key={row.job.job_id} className="text-error">
              {jobDisplayName(row.job)}: {row.error}
            </p>
          ))}
          {paths.length > 0 && (
            <>
              <ul className="max-h-48 overflow-auto rounded-[6px] border border-hairline bg-canvas-soft divide-y divide-hairline">
                {paths.map((row) => (
                  <li
                    key={`${row.locator}-${row.run_id || ""}`}
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
                {formatBytes(bytes)} total
                {cascade
                  ? ` · ${cascade} attempt${cascade === 1 ? "" : "s"}`
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
            disabled={busy || loading || ready.length === 0}
          >
            {busy ? "Deleting..." : bulk ? `Delete ${ready.length}` : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}
