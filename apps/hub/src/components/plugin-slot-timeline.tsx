import { useMemo, useState } from "react";

import type { DeclaredSlot, PluginPreview } from "@/lib/api";
import { cn } from "@/lib/utils";

const SLOT_LEVEL: Record<string, number> = {
  before_prepare: 0,
  after_prepare: 0,
  before_run: 0,
  after_run: 0,
  before_evaluate: 0,
  after_evaluate: 0,
  before_cleanup: 0,
  after_cleanup: 0,
  image_contribute: 1,
  env_prepare_commands: 1,
  env_inject: 1,
  env_action: 1,
  env_teardown_commands: 1,
  executor: 2,
  before_agent_open: 2,
  after_agent_open: 2,
  before_agent_invoke: 2,
  after_agent_invoke: 2,
  before_agent_close: 2,
  after_agent_close: 2,
  normalize_agent_result: 2,
  evaluation_input_contribute: 3,
  evaluation_runtime: 3,
  score_postprocess: 3,
  trajectory_collect: 4,
  trajectory_enrich: 4,
  trajectory_seal: 4,
  evidence_extra: 4,
  cleanup_actions: 5,
  cleanup_report: 5,
};

/** Prefer registry `declared`; fall back to provide/on chip ids. */
export function declaredSlotsFromPreview(
  preview: PluginPreview | null,
): DeclaredSlot[] {
  const listed = preview?.declared;
  if (Array.isArray(listed) && listed.length) {
    return listed.map((d) => ({
      ...d,
      level: typeof d.level === "number" ? d.level : SLOT_LEVEL[d.id],
    }));
  }
  const out: DeclaredSlot[] = [];
  for (const id of preview?.slots?.provide || []) {
    out.push({ id, kind: "provide", level: SLOT_LEVEL[id] });
  }
  for (const id of preview?.slots?.on || []) {
    out.push({ id, kind: "on", level: SLOT_LEVEL[id] });
  }
  return out;
}

const LEVEL_LABELS = [
  "Attempt / phase bookends",
  "Environment and image",
  "Agent executor and session",
  "Evaluation adjacency",
  "Trajectory and evidence",
  "Cleanup",
] as const;

const SLOT_BLURBS: Record<string, string> = {
  before_prepare: "Runs before Attempt prepare.",
  after_prepare: "Runs after Attempt prepare.",
  before_run: "Runs before the harness/worker.",
  after_run: "Runs after the harness/worker.",
  before_evaluate: "Runs before the evaluator barrier.",
  after_evaluate: "Runs after evaluation, still not PASS authority.",
  before_cleanup: "Runs before cleanup.",
  after_cleanup: "Runs after cleanup.",
  image_contribute: "Contribute Dockerfile fragments at L1 bake.",
  env_prepare_commands: "Merge environment prepare commands.",
  env_inject: "Contribute environment injection.",
  env_action: "Provide the environment action gate.",
  env_teardown_commands: "Merge environment teardown commands.",
  executor: "Provide the Agent executor SPI for this plugin id.",
  before_agent_open: "Hook before the parent opens an Agent session.",
  after_agent_open: "Hook after the parent opens an Agent session.",
  before_agent_invoke: "Hook before session.invoke.",
  after_agent_invoke: "Hook after session.invoke.",
  before_agent_close: "Hook before the parent closes the executor.",
  after_agent_close: "Hook after the parent closes the executor.",
  normalize_agent_result: "Normalize vendor AgentResult before evidence.",
  evaluation_input_contribute: "Contribute evaluator-only input before the barrier.",
  evaluation_runtime: "Provide the evaluation runtime adapter.",
  score_postprocess: "Post-process scores after the independent evaluator.",
  trajectory_collect: "Collect extra trajectory material.",
  trajectory_enrich: "Enrich sealed trajectory rows.",
  trajectory_seal: "Provide trajectory seal (observational, not PASS).",
  evidence_extra: "Attach extra evidence files.",
  cleanup_actions: "Extra cleanup actions after the Attempt.",
  cleanup_report: "Report leftover cleanup state.",
};

export function resolvePluginEntryPath(
  entry: string | undefined,
  files: string[],
): string {
  const fallback = files.includes("plugin.yaml")
    ? "plugin.yaml"
    : files[0] || "plugin.yaml";
  if (!entry) return fallback;
  const mod = entry.split(":")[0]?.trim();
  if (!mod) return fallback;
  const rel = `${mod.replaceAll(".", "/")}.py`;
  const hit = files.find(
    (f) => f === rel || f.endsWith(`/${rel}`) || f.endsWith(rel),
  );
  return hit || fallback;
}

function declaredForLevel(declared: DeclaredSlot[], level: number): DeclaredSlot[] {
  return declared.filter((d) => d.level === level);
}

export function PluginSlotTimeline({
  declared,
  files,
  onOpenPath,
}: {
  declared: DeclaredSlot[];
  files: string[];
  onOpenPath: (path: string) => void;
}) {
  const affected = useMemo(() => {
    const set = new Set<number>();
    for (const d of declared) {
      if (typeof d.level === "number") set.add(d.level);
    }
    return set;
  }, [declared]);
  const firstAffected = [...affected].sort((a, b) => a - b)[0];
  const [openLevel, setOpenLevel] = useState<number | null>(
    firstAffected ?? 0,
  );

  if (!declared.length) {
    return (
      <p className="text-sm text-mute">
        No slot preview available (open{" "}
        <span className="font-mono text-xs">plugin.yaml</span> in files).
      </p>
    );
  }

  return (
    <div className="rounded-[8px] border border-hairline bg-canvas-soft">
      <ol className="divide-y divide-hairline">
        {LEVEL_LABELS.map((label, level) => {
          const slots = declaredForLevel(declared, level);
          const hit = affected.has(level);
          const open = openLevel === level;
          return (
            <li key={level}>
              <button
                type="button"
                onClick={() => setOpenLevel(open ? null : level)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 text-left",
                  hit ? "text-ink" : "text-mute",
                  open && "bg-canvas",
                )}
              >
                <span
                  className={cn(
                    "font-mono text-[11px] w-6 shrink-0",
                    hit ? "text-ink" : "text-mute",
                  )}
                >
                  L{level}
                </span>
                <span
                  className={cn(
                    "h-2.5 w-2.5 rounded-full border shrink-0",
                    hit
                      ? "bg-ink border-ink"
                      : "bg-transparent border-hairline-strong",
                  )}
                  aria-hidden
                />
                <span className="text-sm">{label}</span>
                {hit ? (
                  <span className="ml-auto font-mono text-[11px] tabular-nums text-mute">
                    {slots.length} slot{slots.length === 1 ? "" : "s"}
                  </span>
                ) : (
                  <span className="ml-auto text-[11px] text-mute">—</span>
                )}
              </button>
              {open && hit ? (
                <ul className="px-3 pb-3 space-y-2">
                  {slots.map((slot) => {
                    const path = resolvePluginEntryPath(slot.entry, files);
                    return (
                      <li
                        key={`${slot.kind}-${slot.id}`}
                        className="rounded-[6px] border border-hairline bg-canvas px-3 py-2 space-y-1"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-ink">
                            {slot.id}
                          </span>
                          <span className="text-[10px] uppercase tracking-wide text-mute border border-hairline rounded px-1.5 py-0.5">
                            {slot.kind}
                          </span>
                        </div>
                        <p className="text-xs text-body">
                          {SLOT_BLURBS[slot.id] ||
                            "Declared extension slot (not a job execution trace)."}
                        </p>
                        {slot.entry ? (
                          <p className="font-mono text-[11px] text-mute">
                            {slot.entry}
                          </p>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => onOpenPath(path)}
                          className="text-xs text-body underline underline-offset-2 hover:text-ink"
                        >
                          Open {path}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {open && !hit ? (
                <p className="px-3 pb-3 text-xs text-mute">
                  This plugin does not declare slots on L{level}.
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
