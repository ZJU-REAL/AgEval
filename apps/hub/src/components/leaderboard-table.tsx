import { CommandStrip } from "@/components/command-strip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SuiteRow } from "@/lib/api";
import { formatScore } from "@/lib/utils";

/**
 * Dataset Leaderboard (#40). Observational aggregates only — never suite PASS.
 * Heterogeneous configs (config_homogeneous === false) are excluded from ranking.
 */
export function LeaderboardTable({
  suites,
  databaseId,
}: {
  suites: SuiteRow[];
  databaseId: string;
}) {
  const comparable = suites.filter((s) => s.config_homogeneous !== false);
  const skipped = suites.length - comparable.length;

  // Prefer higher pass_rate, then mean_score, then newer created_at
  const rows = [...comparable].sort((a, b) => {
    const pr = (b.pass_rate ?? -1) - (a.pass_rate ?? -1);
    if (pr !== 0) return pr;
    const ms = (b.mean_score ?? -1) - (a.mean_score ?? -1);
    if (ms !== 0) return ms;
    return (Number(b.created_at) || 0) - (Number(a.created_at) || 0);
  });

  if (suites.length === 0) {
    return (
      <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
        <p className="text-sm font-medium text-ink">No Leaderboard rows yet</p>
        <p className="text-sm text-mute">
          Upload suite aggregates with{" "}
          <code className="font-mono">bora results upload-suite</code>. These
          are observational metrics — not a suite-level PASS.
        </p>
        <CommandStrip
          command={`bora results upload-suite <database-root> --suite-run-id <id> --public`}
        />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-2">
        <p className="text-sm font-medium text-ink">
          Configuration inconsistent — hard to compare
        </p>
        <p className="text-sm text-mute">
          All uploaded suites for <span className="font-mono">{databaseId}</span>{" "}
          have <code className="font-mono">config_homogeneous: false</code> (or
          mixed configs). They remain visible in Task Jobs lists but are not
          ranked here. See packing guidance in{" "}
          <code className="font-mono">$bora-config-package</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {skipped > 0 ? (
        <p className="text-xs text-mute">
          {skipped} suite{skipped === 1 ? "" : "s"} hidden (config not
          homogeneous — not comparable on this board).
        </p>
      ) : null}
      <p className="text-xs text-mute">
        Observational aggregates only. Per-task evaluator owns PASS — never
        treat this table as suite PASS authority.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Agent</TableHead>
            <TableHead>Model</TableHead>
            <TableHead className="text-right">Pass rate</TableHead>
            <TableHead className="text-right">Mean score</TableHead>
            <TableHead className="text-right">Tasks</TableHead>
            <TableHead>Visibility</TableHead>
            <TableHead>Suite run</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((s) => {
            const m = s.metrics || {};
            const nTasks =
              typeof m.n_tasks === "number"
                ? m.n_tasks
                : Array.isArray(s.task_refs)
                  ? s.task_refs.length
                  : null;
            const nPass = typeof m.n_pass === "number" ? m.n_pass : null;
            return (
              <TableRow key={s.suite_run_id}>
                <TableCell className="text-sm">
                  {s.agent_label || "—"}
                  {s.config_fingerprint ? (
                    <span
                      className="block text-[10px] font-mono text-mute truncate max-w-[16ch]"
                      title={s.config_fingerprint}
                    >
                      {s.config_fingerprint.slice(0, 18)}…
                    </span>
                  ) : s.config_homogeneous == null ? (
                    <span className="block text-[10px] text-mute">
                      missing config fingerprint
                    </span>
                  ) : null}
                </TableCell>
                <TableCell className="text-sm font-mono text-xs">
                  {s.model_label || "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {s.pass_rate == null
                    ? "—"
                    : `${(Number(s.pass_rate) * 100).toFixed(1)}%`}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatScore(s.mean_score)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-xs">
                  {nPass != null && nTasks != null
                    ? `${nPass}/${nTasks}`
                    : nTasks != null
                      ? String(nTasks)
                      : "—"}
                </TableCell>
                <TableCell className="text-sm text-body">
                  {s.visibility || "—"}
                </TableCell>
                <TableCell className="font-mono text-[11px]">
                  {s.suite_run_id}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
