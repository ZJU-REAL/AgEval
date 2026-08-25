import { ChevronLeft, ChevronRight } from "lucide-react";

import { HoverTip } from "@/components/hover-tip";
import { useDocumentTitle } from "@/lib/document-title";
import {
  SlotHistorySelect,
  type SlotHistoryEntry,
} from "@/components/trial/slot-history-select";
import { Button } from "@/components/ui/button";
import type { Trial } from "@/lib/api";

export function TrialHeader({
  runId,
  taskId,
  trial,
  prevId,
  nextId,
  onSibling,
  slotCurrentRunId,
  slotCurrentStartedAt,
  slotPrevious,
  onSlotSelect,
}: {
  runId: string;
  taskId: string;
  trial: Trial | null;
  prevId: string | null;
  nextId: string | null;
  onSibling: (id: string | null) => void;
  slotCurrentRunId?: string | null;
  slotCurrentStartedAt?: string | null;
  slotPrevious?: SlotHistoryEntry[];
  onSlotSelect?: (id: string) => void;
}) {
  useDocumentTitle(runId);

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink font-mono truncate">
          {runId}
        </h1>
        {/* Same mute/body style: task · framework · environment · upstream(if any) */}
        <p className="text-xs text-mute mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>
            task <span className="text-body font-medium">{taskId}</span>
          </span>
          {trial?.dataset_ref ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <span className="text-body font-medium">
                {trial.dataset_ref}
              </span>
            </>
          ) : null}
          {trial?.framework ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <span className="text-body font-medium">
                {trial.framework}
              </span>
            </>
          ) : null}
          {trial?.environment ? (
            <>
              <span className="text-mute select-none" aria-hidden>
                ·
              </span>
              <span className="text-body font-medium">
                {trial.environment}
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
                  className="text-link hover:text-link-deep truncate max-w-[min(48ch,100%)]"
                >
                  {trial.upstream_url}
                </a>
              </HoverTip>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {onSlotSelect ? (
          <SlotHistorySelect
            viewingRunId={runId}
            currentRunId={slotCurrentRunId}
            previous={slotPrevious}
            currentAt={slotCurrentStartedAt ?? trial?.started}
            onSelect={onSlotSelect}
          />
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={!prevId}
          onClick={() => onSibling(prevId)}
          aria-label="Previous trial"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={!nextId}
          onClick={() => onSibling(nextId)}
          aria-label="Next trial"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
