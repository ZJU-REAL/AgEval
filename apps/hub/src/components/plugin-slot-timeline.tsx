import { HoverTip } from "@/components/hover-tip";
import type { DeclaredSlot, PluginPreview } from "@/lib/api";

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
  home_overlay: 1,
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
  if (!declared.length) {
    return (
      <p className="text-sm text-mute">
        No slot preview available (open{" "}
        <span className="font-mono text-xs">plugin.yaml</span> in files).
      </p>
    );
  }

  return (
    <div className="rounded-[8px] border border-hairline bg-canvas overflow-hidden">
      <ol className="divide-y divide-hairline">
        {LEVEL_LABELS.map((label, level) => {
          const slots = declaredForLevel(declared, level);
          const hit = slots.length > 0;
          return (
            <li
              key={level}
              className={
                hit
                  ? "flex items-center gap-3 px-3 py-2.5 text-ink bg-canvas-soft"
                  : "flex items-center gap-3 px-3 py-2.5 text-mute bg-canvas"
              }
            >
              <span className="font-mono text-[11px] w-6 shrink-0">
                L{level}
              </span>
              <span
                className={
                  hit
                    ? "h-2 w-2 rounded-full border border-mute bg-mute/70 shrink-0"
                    : "h-2 w-2 rounded-full border border-hairline-strong bg-transparent shrink-0"
                }
                aria-hidden
              />
              <span className="text-sm shrink-0">{label}</span>
              {hit ? (
                <span className="ml-auto flex min-w-0 flex-wrap justify-end gap-x-3 gap-y-1">
                  {slots.map((slot) => {
                    const path = resolvePluginEntryPath(slot.entry, files);
                    return (
                      <HoverTip content={path}>
                      <button
                        key={`${slot.kind}-${slot.id}`}
                        type="button"
                        onClick={() => onOpenPath(path)}
                        className="cursor-pointer font-mono text-xs text-ink underline-offset-2 hover:underline hover:decoration-mute"
                      >
                        {slot.id}
                      </button>
                      </HoverTip>
                    );
                  })}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
