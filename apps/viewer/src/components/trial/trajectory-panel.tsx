import { useMemo, type ComponentType } from "react";
import {
  Bot,
  Eye,
  FilePenLine,
  FileSearch,
  Flag,
  MessageSquare,
  Shield,
  Terminal,
  User,
  Wrench,
} from "lucide-react";

import type { TrajectoryStep } from "@/lib/api";
import { cn } from "@/lib/utils";

import { actorLabel, type ActorRow } from "./types";

type IconComp = ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

function stepIcon(opts: {
  isUser: boolean;
  isAsst: boolean;
  isToolCall: boolean;
  isObservation: boolean;
  isTerminal: boolean;
  isPermission: boolean;
  kind?: string | null;
  functionName?: string | null;
}): IconComp {
  if (opts.isUser) return User;
  if (opts.isAsst) return Bot;
  if (opts.isObservation) return Eye;
  if (opts.isTerminal) return Flag;
  if (opts.isPermission) return Shield;
  if (opts.isToolCall) {
    const k = (opts.kind || opts.functionName || "").toLowerCase();
    if (k === "execute" || k === "bash" || k === "shell") return Terminal;
    if (k === "read" || k === "search" || k === "fetch") return FileSearch;
    if (k === "edit" || k === "write" || k === "delete" || k === "move")
      return FilePenLine;
    return Wrench;
  }
  return MessageSquare;
}

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
          const stepType = (s.type || "").toString();
          const isToolCall = stepType === "tool_call";
          const isObservation = stepType === "observation";
          const isPermission = stepType === "permission_decision";
          const role = (
            s.role ||
            (isToolCall
              ? "tool_call"
              : isObservation
                ? "observation"
                : isPermission
                  ? "permission"
                  : stepType || "event")
          ).toString();
          const isUser = role === "user";
          const isAsst = role === "assistant";
          const isTerminal = stepType === "terminal";
          const label = isToolCall
            ? s.function_name || s.kind || s.title || "tool_call"
            : isObservation
              ? "observation"
              : role;
          const Icon = stepIcon({
            isUser,
            isAsst,
            isToolCall,
            isObservation,
            isTerminal,
            isPermission,
            kind: s.kind,
            functionName: s.function_name,
          });
          const body =
            s.content ||
            (isToolCall && s.args != null
              ? typeof s.args === "string"
                ? s.args
                : JSON.stringify(s.args, null, 2)
              : null) ||
            (isToolCall && s.title ? s.title : null) ||
            (isObservation && s.raw_output != null
              ? typeof s.raw_output === "string"
                ? s.raw_output
                : JSON.stringify(s.raw_output, null, 2)
              : null);
          // Success is the common case for folded tool/observation rows; only
          // surface non-success status (failed / error / cancelled / …).
          const statusRaw =
            typeof s.status === "string" ? s.status.trim() : "";
          const statusLower = statusRaw.toLowerCase();
          const showStatus =
            Boolean(statusRaw) &&
            !["completed", "complete", "success", "ok", "done"].includes(
              statusLower,
            );

          return (
            <li
              key={`${s.invocation || ""}-${s.line || i}-${i}`}
              className={cn(
                "rounded-[8px] border border-hairline px-3 py-2.5",
                isTerminal && "bg-canvas-soft",
                isObservation && "bg-canvas-soft/40",
              )}
            >
              <div className="flex items-start gap-3 text-xs mb-1">
                <div className="flex flex-wrap items-center gap-2 min-w-0">
                  <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-wide text-ink">
                    <Icon
                      className="h-3.5 w-3.5 shrink-0 opacity-80"
                      aria-hidden
                    />
                    {label}
                  </span>
                  {showProfileBadge && s.profile_id ? (
                    <span className="rounded bg-canvas-soft border border-hairline px-1.5 py-0 font-mono text-[11px] text-body font-normal normal-case tracking-normal">
                      {s.profile_id}
                    </span>
                  ) : null}
                  {s.kind && isToolCall && s.kind !== label ? (
                    <span className="rounded bg-canvas-soft border border-hairline px-1.5 py-0 font-mono text-[11px] text-mute font-normal normal-case tracking-normal">
                      {s.kind}
                    </span>
                  ) : null}
                </div>
                <div className="ml-auto flex flex-col items-end gap-0.5 min-w-0 max-w-[min(100%,36rem)] text-right text-mute font-mono font-normal normal-case tracking-normal">
                  {showStatus ? (
                    <span
                      className={cn(
                        statusLower.includes("fail") ||
                          statusLower.includes("error") ||
                          statusLower.includes("cancel")
                          ? "text-error"
                          : undefined,
                      )}
                    >
                      {statusRaw}
                    </span>
                  ) : null}
                  {s.tool_call_id ? (
                    <span className="break-all" title={s.tool_call_id}>
                      {s.tool_call_id}
                    </span>
                  ) : null}
                  {s.turn_index != null ? <span>turn {s.turn_index}</span> : null}
                  {s.invocation ? (
                    <span className="break-all" title={s.invocation}>
                      {s.invocation}
                    </span>
                  ) : null}
                  {s.stop_reason ? <span>{s.stop_reason}</span> : null}
                  {s.ok === false ? (
                    <span className="text-error">not ok</span>
                  ) : null}
                </div>
              </div>
              {body ? (
                <pre className="m-0 whitespace-pre-wrap break-words font-mono text-[13px] leading-5 text-body">
                  {body}
                </pre>
              ) : s.error ? (
                <p className="text-sm text-error">{String(s.error)}</p>
              ) : isTerminal ? (
                <p className="text-sm text-mute">terminal</p>
              ) : isToolCall || isObservation ? (
                <p className="text-sm text-mute">
                  {isToolCall ? "tool call (no args)" : "observation (empty)"}
                </p>
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
