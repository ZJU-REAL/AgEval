import {
  useEffect,
  useMemo,
  useState,
  type ComponentType,
  type MouseEvent,
} from "react";
import {
  BotMessageSquare,
  Brain,
  Check,
  Copy,
  Eye,
  FilePenLine,
  FileSearch,
  FoldVertical,
  UnfoldVertical,
  MessageSquare,
  Shield,
  SquareTerminal,
  User,
  Wrench,
} from "lucide-react";

import { HoverTip } from "@/components/hover-tip";
import type { TrajectoryStep } from "@/lib/trial-types";
import { cn } from "@/lib/utils";

import { actorLabel, type ActorRow } from "./types";

type IconComp = ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

const LONG_BODY_CHARS = 240;
const LONG_BODY_LINES = 4;

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

function stepElapsedMs(s: {
  elapsed_ms?: number | null;
  metadata?: Record<string, unknown> | null;
}): number | null {
  const direct = asFiniteNumber(s.elapsed_ms);
  if (direct != null && direct >= 0) return direct;
  const lat = asFiniteNumber(s.metadata?.latency_ms);
  if (lat != null && lat >= 0) return lat;
  return null;
}

function formatElapsedMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalS = ms / 1000;
  if (totalS < 10) return `${totalS.toFixed(1)}s`;
  if (totalS < 60) return `${Math.round(totalS)}s`;
  const minutes = Math.floor(totalS / 60);
  const seconds = Math.round(totalS - minutes * 60);
  if (seconds === 60) return `${minutes + 1}m`;
  return seconds ? `${minutes}m ${String(seconds).padStart(2, "0")}s` : `${minutes}m`;
}

function bodyIsLong(body: string): boolean {
  return body.length > LONG_BODY_CHARS || body.split("\n").length > LONG_BODY_LINES;
}

function CopyBodyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function onCopy(e: MouseEvent<HTMLButtonElement>) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }
  return (
    <HoverTip content={copied ? "Copied" : "Copy"}>
    <button
      type="button"
      onClick={onCopy}
      aria-label={copied ? "Copied" : "Copy step"}
      className="shrink-0 rounded-[4px] p-0.5 text-mute hover:bg-row-hover hover:text-ink"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
    </HoverTip>
  );
}

function StepBody({
  body,
  collapsible,
  defaultCollapsed,
  expandAll,
  expandGen,
}: {
  body: string;
  collapsible: boolean;
  defaultCollapsed: boolean;
  expandAll: boolean;
  expandGen: number;
}) {
  const [open, setOpen] = useState(!defaultCollapsed);
  const preview = body.split("\n")[0]?.slice(0, 160) || "";

  useEffect(() => {
    if (expandGen === 0) return;
    setOpen(expandAll);
  }, [expandAll, expandGen]);

  if (!collapsible) {
    return (
      <pre className="m-0 px-3 pb-2.5 whitespace-pre-wrap break-words font-mono text-[13px] leading-5 text-body">
        {body}
      </pre>
    );
  }

  function toggle() {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.toString()) return;
    setOpen((v) => !v);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-expanded={open}
      className="block w-full cursor-pointer px-3 py-2.5 text-left hover:bg-row-hover"
    >
      {open ? (
        <pre className="m-0 whitespace-pre-wrap break-words font-mono text-[13px] leading-5 text-body">
          {body}
        </pre>
      ) : (
        <pre className="m-0 truncate font-mono text-[13px] leading-5 text-mute">
          {preview}
          {body.length > preview.length ? "…" : ""}
        </pre>
      )}
    </button>
  );
}

function stepIcon(opts: {
  isUser: boolean;
  isAsst: boolean;
  isThought: boolean;
  isToolCall: boolean;
  isObservation: boolean;
  isTerminal: boolean;
  isPermission: boolean;
  kind?: string | null;
  functionName?: string | null;
}): IconComp {
  if (opts.isUser) return User;
  if (opts.isThought) return Brain;
  if (opts.isAsst) return BotMessageSquare;
  if (opts.isObservation) return Eye;
  if (opts.isTerminal) return SquareTerminal;
  if (opts.isPermission) return Shield;
  if (opts.isToolCall) {
    const k = (opts.kind || opts.functionName || "").toLowerCase();
    if (k === "execute" || k === "bash" || k === "shell") return SquareTerminal;
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
  const actorByPid = useMemo(() => {
    return new Map(
      actors.map((a) => [a.profile_id || `${a.role}-${a.agent}`, a]),
    );
  }, [actors]);
  const multiRole = useMemo(() => {
    const ids = new Set<string>();
    for (const s of steps) {
      if (typeof s.profile_id === "string" && s.profile_id) ids.add(s.profile_id);
    }
    if (ids.size >= 2) return true;
    const actorIds = new Set(
      actors
        .map((a) => a.profile_id)
        .filter((p): p is string => typeof p === "string" && !!p),
    );
    return actorIds.size >= 2;
  }, [steps, actors]);
  const invokes = useMemo(() => {
    type Block = {
      turn: number | null;
      profileId: string | null;
      steps: TrajectoryStep[];
    };
    const blocks: Block[] = [];
    for (const s of steps) {
      const turn = typeof s.turn_index === "number" ? s.turn_index : null;
      const pid =
        typeof s.profile_id === "string" && s.profile_id ? s.profile_id : null;
      const last = blocks[blocks.length - 1];
      if (last && last.turn != null && last.turn === turn) {
        last.steps.push(s);
        if (!last.profileId && pid) last.profileId = pid;
        continue;
      }
      blocks.push({ turn, profileId: pid, steps: [s] });
    }
    return blocks;
  }, [steps]);
  const showInvokeHeaders = multiRole && invokes.length >= 2;
  const [allExpanded, setAllExpanded] = useState(false);
  const [expandGen, setExpandGen] = useState(0);

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

  function renderSteps(list: TrajectoryStep[], hideTurnIndex = false) {
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
          const isThought = (s.part || "").toString() === "thought";
          const isAsst = role === "assistant" && !isThought;
          const isTerminal = stepType === "terminal";
          const label = isToolCall
            ? s.function_name || s.kind || s.title || "tool_call"
            : isObservation
              ? "observation"
              : isThought
                ? "thought"
                : isAsst
                  ? "agent"
                  : role;
          const Icon = stepIcon({
            isUser,
            isAsst,
            isThought,
            isToolCall,
            isObservation,
            isTerminal,
            isPermission,
            kind: s.kind,
            functionName: s.function_name,
          });
          const toolArgsEmpty =
            s.args == null ||
            (typeof s.args === "object" &&
              !Array.isArray(s.args) &&
              Object.keys(s.args).length === 0);
          let body: string | null =
            s.content ||
            (isToolCall && !toolArgsEmpty
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

          // permission / terminal: synthesize body from structured fields when needed
          if (!body && isPermission) {
            const bits = [
              s.policy != null && s.policy !== "" ? `policy=${s.policy}` : null,
              s.outcome != null && s.outcome !== "" ? `outcome=${s.outcome}` : null,
              s.option_id != null && s.option_id !== ""
                ? `option_id=${s.option_id}`
                : null,
            ].filter(Boolean) as string[];
            body = bits.length ? bits.join(" · ") : null;
          }
          if (!body && isTerminal) {
            const bits: string[] = [];
            if (s.ok === true) bits.push("ok");
            else if (s.ok === false) bits.push("not ok");
            if (s.stop_reason) bits.push(`stop=${s.stop_reason}`);
            if (s.error) bits.push(`error=${String(s.error)}`);
            if (s.metadata && typeof s.metadata === "object") {
              const meta = s.metadata;
              const metaBits = (
                [
                  "executor_kind",
                  "acp_entry_id",
                  "actual_model",
                  "locked_model",
                  "protocol_version",
                ] as const
              )
                .filter((k) => meta[k] != null && meta[k] !== "")
                .map((k) => `${k}=${String(meta[k])}`);
              if (metaBits.length) bits.push(metaBits.join(" "));
            }
            body = bits.length ? bits.join(" · ") : null;
          }
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
                "overflow-hidden rounded-[8px] border border-hairline",
                isObservation && "bg-canvas-soft/40",
              )}
            >
              <div className="flex items-start gap-3 px-3 pt-2.5 pb-1 text-xs">
                <div className="flex flex-wrap items-center gap-2 min-w-0">
                  <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-wide text-ink">
                    <Icon
                      className="h-3.5 w-3.5 shrink-0 opacity-80"
                      aria-hidden
                    />
                    {label}
                  </span>
                  {!hideTurnIndex && s.turn_index != null ? (
                    <span className="text-mute font-mono font-normal normal-case tracking-normal">
                      turn {s.turn_index}
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
                  {s.stop_reason ? <span>{s.stop_reason}</span> : null}
                  {s.ok === false ? (
                    <span className="text-error">not ok</span>
                  ) : null}
                  {(() => {
                    const elapsed = stepElapsedMs(s);
                    return elapsed != null ? (
                    <HoverTip content="duration (observational)">
                      <span>{formatElapsedMs(elapsed)}</span>
                    </HoverTip>
                    ) : null;
                  })()}
                </div>
                {body ? <CopyBodyButton text={body} /> : null}
              </div>
              {body ? (
                <StepBody
                  body={body}
                  collapsible={isToolCall || isObservation || bodyIsLong(body)}
                  defaultCollapsed={
                    isToolCall || isObservation || bodyIsLong(body)
                  }
                  expandAll={allExpanded}
                  expandGen={expandGen}
                />
              ) : null}
              {!body && !isTerminal ? (
                s.error ? (
                  <p className="px-3 pb-2.5 text-sm text-error">{String(s.error)}</p>
                ) : isPermission ? (
                  <p className="px-3 pb-2.5 text-sm text-mute">permission (no decision fields)</p>
                ) : isToolCall || isObservation ? (
                  <p className="px-3 pb-2.5 text-sm text-mute">
                    {isToolCall ? "tool call (no args)" : "observation (empty)"}
                  </p>
                ) : null
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
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-mute">
          Trajectory is observational only; independent evaluator owns PASS.
        </p>
        <HoverTip content={allExpanded ? "Collapse all" : "Expand all"}>
        <button
          type="button"
          onClick={() => {
            setAllExpanded((v) => !v);
            setExpandGen((n) => n + 1);
          }}
          aria-label={allExpanded ? "Collapse all" : "Expand all"}
          className="shrink-0 rounded-[4px] p-0.5 text-mute hover:bg-row-hover hover:text-ink"
        >
          {allExpanded ? (
            <FoldVertical className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <UnfoldVertical className="h-3.5 w-3.5" aria-hidden />
          )}
        </button>
        </HoverTip>
      </div>
      {showInvokeHeaders ? (
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {invokes.map((block, i) => {
            const actor = block.profileId
              ? actorByPid.get(block.profileId)
              : undefined;
            const who = block.profileId
              ? actorLabel(actor, block.profileId)
              : null;
            const title =
              block.turn != null
                ? who
                  ? `invoke ${block.turn} · ${who}`
                  : `invoke ${block.turn}`
                : who || "invoke";
            return (
              <section key={`${block.turn ?? "x"}-${i}`} className="space-y-2">
                <h3 className="text-xs font-medium text-ink sticky top-0 bg-canvas/95 backdrop-blur-sm py-1 border-b border-hairline font-mono">
                  {title}
                  <span className="text-mute font-normal ml-2">
                    {block.steps.length} step
                    {block.steps.length === 1 ? "" : "s"}
                  </span>
                </h3>
                {renderSteps(block.steps, true)}
              </section>
            );
          })}
        </div>
      ) : (
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          {renderSteps(steps)}
        </div>
      )}
    </div>
  );
}
