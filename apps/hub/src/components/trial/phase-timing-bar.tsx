/**
 * Harbor-style horizontal phase / token bars with legend + hover labels.
 * Data from Attempt result.phase_timing / token_timing (#47 D).
 */

export type PhaseSeg = {
  id: string;
  label?: string;
  duration_ms?: number;
  tokens?: number;
};

export type PhaseTiming = {
  phases?: PhaseSeg[];
  total_ms?: number;
  started_at?: string | null;
  finished_at?: string | null;
};

export type TokenTiming = {
  segments?: PhaseSeg[];
  total_tokens?: number;
};

const PHASE_COLORS: Record<string, string> = {
  prepare: "bg-zinc-300 dark:bg-zinc-600",
  run: "bg-zinc-500 dark:bg-zinc-400",
  evaluate: "bg-zinc-400 dark:bg-zinc-500",
  cleanup: "bg-zinc-200 dark:bg-zinc-700",
  env_setup: "bg-zinc-300 dark:bg-zinc-600",
  agent_setup: "bg-zinc-500 dark:bg-zinc-400",
  agent_execution: "bg-zinc-500 dark:bg-zinc-400",
  verifier: "bg-zinc-400 dark:bg-zinc-500",
};

const TOKEN_COLORS: Record<string, string> = {
  cached_input: "bg-zinc-300 dark:bg-zinc-600",
  uncached_input: "bg-zinc-500 dark:bg-zinc-400",
  output: "bg-zinc-700 dark:bg-zinc-300",
};

function formatMs(ms: number | undefined | null): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s - m * 60);
  return rem ? `${m}m ${String(rem).padStart(2, "0")}s` : `${m}m`;
}

function formatTokens(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`;
  return String(Math.round(n));
}

function colorFor(id: string, kind: "phase" | "token"): string {
  const map = kind === "phase" ? PHASE_COLORS : TOKEN_COLORS;
  return map[id] || "bg-zinc-400 dark:bg-zinc-500";
}

function SegmentBar({
  title,
  segments,
  totalLabel,
  kind,
  valueKey,
  formatValue,
}: {
  title: string;
  segments: PhaseSeg[];
  totalLabel: string;
  kind: "phase" | "token";
  valueKey: "duration_ms" | "tokens";
  formatValue: (n: number | undefined) => string;
}) {
  const total = segments.reduce((acc, s) => acc + (Number(s[valueKey]) || 0), 0);
  if (total <= 0 && segments.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-medium text-ink">{title}</h3>
        <span className="text-xs tabular text-mute">{totalLabel}</span>
      </div>
      <div
        className="flex h-3 w-full overflow-hidden rounded-[4px] bg-canvas-soft border border-hairline"
        role="img"
        aria-label={`${title}: ${totalLabel}`}
      >
        {segments.map((seg) => {
          const v = Number(seg[valueKey]) || 0;
          const pct = total > 0 ? (v / total) * 100 : 0;
          if (pct <= 0) return null;
          const label = seg.label || seg.id;
          return (
            <div
              key={seg.id}
              className={`${colorFor(seg.id, kind)} h-full min-w-[2px] transition-opacity hover:opacity-90`}
              style={{ width: `${pct}%` }}
              title={`${label}: ${formatValue(v)}`}
            />
          );
        })}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">
        {segments.map((seg) => {
          const v = Number(seg[valueKey]) || 0;
          if (v <= 0 && total > 0) return null;
          return (
            <li key={seg.id} className="inline-flex items-center gap-1.5">
              <span
                className={`inline-block h-2 w-2 rounded-[2px] ${colorFor(seg.id, kind)}`}
                aria-hidden
              />
              <span>{seg.label || seg.id}</span>
              <span className="tabular text-body">{formatValue(v)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function PhaseTimingBar({
  phaseTiming,
  tokenTiming,
}: {
  phaseTiming?: PhaseTiming | null;
  tokenTiming?: TokenTiming | null;
}) {
  const phases = phaseTiming?.phases || [];
  const tokens = (tokenTiming?.segments || []).filter((s) => (s.tokens ?? 0) > 0);

  if (phases.length === 0 && tokens.length === 0) return null;

  return (
    <div className="space-y-4 rounded-[8px] border border-hairline p-4">
      {tokens.length > 0 ? (
        <SegmentBar
          title="Tokens"
          segments={tokens}
          totalLabel={`${formatTokens(tokenTiming?.total_tokens)} tokens`}
          kind="token"
          valueKey="tokens"
          formatValue={formatTokens}
        />
      ) : null}
      {phases.length > 0 ? (
        <SegmentBar
          title="Timing"
          segments={phases}
          totalLabel={formatMs(phaseTiming?.total_ms)}
          kind="phase"
          valueKey="duration_ms"
          formatValue={formatMs}
        />
      ) : null}
    </div>
  );
}
