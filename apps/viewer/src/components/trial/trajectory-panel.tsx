import { useMemo } from "react";

import type { TrajectoryStep } from "@/lib/api";
import { cn } from "@/lib/utils";

import { actorLabel, type ActorRow } from "./types";

export function TrajectoryPanel({
  loading,
  steps,
  note,
  result,
  actors,
}: {
  loading: boolean;
  steps: TrajectoryStep[];
  note: string | null;
  result: Record<string, unknown> | null;
  actors: ActorRow[];
}) {
  const groups = useMemo(() => {
    const actorByPid = new Map(
      actors.map((a) => [a.profile_id || `${a.role}-${a.agent}`, a]),
    );
    const order: string[] = [];
    const byProfile = new Map<string, TrajectoryStep[]>();
    for (const s of steps) {
      const key =
        (typeof s.profile_id === "string" && s.profile_id) || "__ungrouped__";
      if (!byProfile.has(key)) {
        byProfile.set(key, []);
        order.push(key);
      }
      byProfile.get(key)!.push(s);
    }
    const multi = order.filter((k) => k !== "__ungrouped__").length >= 2;
    return { order, byProfile, actorByPid, multi };
  }, [steps, actors]);

  if (loading) return <p className="text-sm text-mute">Loading trajectory…</p>;
  if (!steps.length) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-mute">No trajectory.jsonl steps for this run.</p>
        {result ? (
          <pre className="text-[12px] font-mono bg-canvas-soft border border-hairline rounded-[8px] p-3 overflow-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        ) : null}
      </div>
    );
  }

  function renderSteps(list: TrajectoryStep[], showProfileBadge: boolean) {
    return (
      <ol className="space-y-2">
        {list.map((s, i) => {
          const role = (s.role || s.type || "event").toString();
          const isUser = role === "user";
          const isAsst = role === "assistant";
          const isTerminal = s.type === "terminal";
          return (
            <li
              key={`${s.invocation || ""}-${s.line || i}-${i}`}
              className={cn(
                "rounded-[8px] border border-hairline px-3 py-2.5",
                isTerminal && "bg-canvas-soft",
              )}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs text-mute mb-1">
                <span
                  className={cn(
                    "font-medium uppercase tracking-wide",
                    isUser && "text-link",
                    isAsst && "text-ink",
                    isTerminal && "text-mute",
                  )}
                >
                  {role}
                </span>
                {showProfileBadge && s.profile_id ? (
                  <span className="rounded bg-canvas-soft border border-hairline px-1.5 py-0 font-mono text-[11px] text-body">
                    {s.profile_id}
                  </span>
                ) : null}
                {s.turn_index != null ? <span>turn {s.turn_index}</span> : null}
                {s.invocation ? (
                  <span className="font-mono truncate max-w-[24ch]">{s.invocation}</span>
                ) : null}
                {s.stop_reason ? <span>{s.stop_reason}</span> : null}
                {s.ok === false ? <span className="text-error">not ok</span> : null}
              </div>
              {s.content ? (
                <pre className="m-0 whitespace-pre-wrap break-words font-mono text-[13px] leading-5 text-body">
                  {s.content}
                </pre>
              ) : s.error ? (
                <p className="text-sm text-error">{String(s.error)}</p>
              ) : isTerminal ? (
                <p className="text-sm text-mute">terminal</p>
              ) : null}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <div className="space-y-3">
      {note ? <p className="text-xs text-mute">{note}</p> : null}
      <p className="text-[11px] text-mute">
        Trajectory is observational only; independent evaluator owns PASS.
      </p>
      {groups.multi ? (
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {groups.order.map((pid) => {
            const list = groups.byProfile.get(pid) || [];
            const actor =
              pid === "__ungrouped__" ? undefined : groups.actorByPid.get(pid);
            const title =
              pid === "__ungrouped__" ? "ungrouped" : actorLabel(actor, pid);
            return (
              <section key={pid} className="space-y-2">
                <h3 className="text-xs font-medium text-ink sticky top-0 bg-canvas/95 backdrop-blur-sm py-1 border-b border-hairline font-mono">
                  {title}
                  <span className="text-mute font-normal ml-2">
                    {list.length} step{list.length === 1 ? "" : "s"}
                  </span>
                </h3>
                {renderSteps(list, false)}
              </section>
            );
          })}
        </div>
      ) : (
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          {renderSteps(steps, false)}
        </div>
      )}
    </div>
  );
}
