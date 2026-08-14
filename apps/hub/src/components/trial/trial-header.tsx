import { HoverTip } from "@/components/hover-tip";
import type { Trial } from "@/lib/trial-types";

/** Header without sibling nav (Hub has no local trial list siblings by default). */
export function TrialHeader({
  runId,
  taskId,
  trial,
}: {
  runId: string;
  taskId: string;
  trial: Trial | null;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink font-mono truncate">
          {runId}
        </h1>
        <p className="text-sm text-mute mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>
            task <span className="text-body font-medium">{taskId}</span>
          </span>
          {trial?.framework ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <span className="text-body font-medium font-mono text-[13px]">
                {trial.framework}
              </span>
            </>
          ) : null}
          {trial?.docker ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <span className="text-body font-medium font-mono text-[13px]">
                {trial.docker}
              </span>
            </>
          ) : null}
          {trial?.upstream_url ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <HoverTip content={trial.upstream_name || trial.upstream_url}>
                <a
                  href={trial.upstream_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-link hover:text-link-deep font-mono text-[13px] truncate max-w-[min(48ch,100%)]"
                >
                  {trial.upstream_url}
                </a>
              </HoverTip>
            </>
          ) : null}
        </p>
      </div>
    </div>
  );
}
