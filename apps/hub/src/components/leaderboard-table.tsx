import { Check, Copy } from "lucide-react";
import { Fragment, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SuiteRow } from "@/lib/api";
import { CodeHighlight } from "@/lib/code-highlight";
import {
  formatPassMetric,
  metricsNAttempts,
  passAtPrimaryK,
  passPowerPrimaryK,
  primaryDisplayK,
} from "@/lib/suite-metrics";
import { formatScore } from "@/lib/utils";

/** Render secret-free job_overlay as bora.profiles/1 YAML for rehydrate display. */
function jobOverlayToProfilesYaml(overlay: SuiteRow["job_overlay"]): string {
  const bindings = overlay?.bindings;
  if (!bindings || typeof bindings !== "object") {
    return "# no job_overlay on this suite\n";
  }
  const lines: string[] = ["format: bora.profiles/1", "bindings:"];
  const roles = Object.keys(bindings).sort();
  if (roles.length === 0) {
    lines.push("  {}");
    return lines.join("\n") + "\n";
  }
  for (const role of roles) {
    const b = bindings[role];
    if (!b || typeof b !== "object") continue;
    lines.push(`  ${role}:`);
    if (b.executor != null) lines.push(`    executor: ${String(b.executor)}`);
    if (b.options && typeof b.options === "object" && b.options.entry != null) {
      lines.push("    options:");
      lines.push(`      entry: ${String(b.options.entry)}`);
    }
    if (b.model != null) lines.push(`    model: ${String(b.model)}`);
    if (b.base_url != null) lines.push(`    base_url: ${String(b.base_url)}`);
    // Locator name only — never a secret value.
    if (b.api_key != null) lines.push(`    api_key: ${String(b.api_key)}`);
  }
  return lines.join("\n") + "\n";
}

function CodeBlock({
  path,
  content,
  maxHeightClass = "max-h-56",
}: {
  path: string;
  content: string;
  maxHeightClass?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="relative rounded-[6px] border border-hairline bg-code-bg">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onCopy}
        aria-label="Copy"
        className="absolute right-1.5 top-1.5 z-10 h-7 w-7 shrink-0"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-ink" />
        ) : (
          <Copy className="h-3.5 w-3.5 text-mute" />
        )}
      </Button>
      <pre
        className={`m-0 overflow-auto p-3 pr-10 font-mono text-[12px] leading-5 whitespace-pre ${maxHeightClass}`}
      >
        <code>
          <CodeHighlight path={path} content={content} />
        </code>
      </pre>
    </div>
  );
}

/**
 * Dataset Leaderboard (#40 + #59 + #60).
 * Rank by observational metrics only — never suite PASS.
 * Job axis = profiles.yaml / job_overlay (not per-task role topology).
 *
 * Sort policy (default): pass_rate desc → mean_score desc → created_at desc.
 * pass@k / pass^k columns are display-only (primary k = max k_values / n_attempts);
 * they do not change job identity or default sort.
 */
export function LeaderboardTable({
  suites,
  databaseId,
}: {
  suites: SuiteRow[];
  databaseId: string;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  const rows = [...suites].sort((a, b) => {
    const pr = (b.pass_rate ?? -1) - (a.pass_rate ?? -1);
    if (pr !== 0) return pr;
    const ms = (b.mean_score ?? -1) - (a.mean_score ?? -1);
    if (ms !== 0) return ms;
    return (Number(b.created_at) || 0) - (Number(a.created_at) || 0);
  });

  // Show k columns when any row has recoverable k metrics (or always with fixtures).
  const showKColumns = rows.some((s) => primaryDisplayK(s.metrics || {}) != null);
  // Agent + Model + Pass rate + Mean + [n_att + pass@k + pass^k] + Tasks + Vis + Suite
  const colCount = showKColumns ? 10 : 7;

  if (suites.length === 0) {
    return (
      <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
        <p className="text-sm font-medium text-ink">No Leaderboard rows yet</p>
        <p className="text-sm text-mute">
          Upload suite aggregates with{" "}
          <code className="font-mono">bora results upload-suite</code>. These
          are observational metrics — not a suite-level PASS. Always-k jobs may
          also show pass@k / pass^k and n_attempts when present in{" "}
          <code className="font-mono">metrics</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-mute">
        Dataset <span className="font-mono">{databaseId}</span> · Observational
        aggregates only (not suite PASS). Job binding is the suite{" "}
        <code className="font-mono">profiles.yaml</code> /{" "}
        <code className="font-mono">job_overlay</code> (role id → entry/model).
        Default sort: Pass rate → Mean score.{" "}
        {showKColumns ? (
          <>
            pass@k / pass^k use the job&apos;s largest k (from{" "}
            <code className="font-mono">k_values</code> /{" "}
            <code className="font-mono">n_attempts</code>); missing →{" "}
            <span className="font-mono">—</span>. k-attempt does not change job
            identity.
          </>
        ) : (
          <>Click a row to view YAML and rehydrate.</>
        )}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Agent / binding</TableHead>
            <TableHead>Model</TableHead>
            <TableHead className="text-right">Pass rate</TableHead>
            <TableHead className="text-right">Mean score</TableHead>
            {showKColumns ? (
              <>
                <TableHead className="text-right">n_attempts</TableHead>
                <TableHead
                  className="text-right"
                  title="Largest k from metrics.k_values / n_attempts; cell labels @k"
                >
                  pass@k
                </TableHead>
                <TableHead
                  className="text-right"
                  title="Same display k as pass@k; cell labels ^k"
                >
                  pass^k
                </TableHead>
              </>
            ) : null}
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
            const open = openId === s.suite_run_id;
            const yamlText = jobOverlayToProfilesYaml(s.job_overlay);
            const rehydrateScript = [
              "# Export this suite's job binding as profiles.yaml (locators only; no secrets)",
              `bora results export-profiles ${s.suite_run_id} --out profiles.from-suite.yaml`,
              "",
              "# Re-run with that binding (fill Database .env locally for credentials)",
              "bora run <database-root> --profiles profiles.from-suite.yaml",
              "",
            ].join("\n");
            const nAtt = metricsNAttempts(m);
            const atK = passAtPrimaryK(m);
            const powK = passPowerPrimaryK(m);

            return (
              <Fragment key={s.suite_run_id}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => setOpenId(open ? null : s.suite_run_id)}
                  data-state={open ? "open" : undefined}
                >
                  <TableCell className="text-sm">
                    {s.agent_label || "—"}
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
                  {showKColumns ? (
                    <>
                      <TableCell className="text-right tabular-nums text-xs">
                        {nAtt == null ? "—" : String(nAtt)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {atK.value == null ? (
                          "—"
                        ) : (
                          <span title={`pass@${atK.k}`}>
                            {formatPassMetric(atK.value)}
                            <span className="ml-1 text-mute">@{atK.k}</span>
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {powK.value == null ? (
                          "—"
                        ) : (
                          <span title={`pass^${powK.k}`}>
                            {formatPassMetric(powK.value)}
                            <span className="ml-1 text-mute">^{powK.k}</span>
                          </span>
                        )}
                      </TableCell>
                    </>
                  ) : null}
                  <TableCell className="text-right tabular-nums text-xs">
                    {nPass != null && nTasks != null
                      ? `${nPass}/${nTasks}`
                      : nTasks != null
                        ? String(nTasks)
                        : "—"}
                  </TableCell>
                  <TableCell className="text-sm text-body">
                    {s.visibility || "—"}
                    {s.uploaded_by ? (
                      <span className="ml-2 font-mono text-[11px] text-mute">
                        by {s.uploaded_by}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-[11px]">
                    {s.suite_run_id}
                  </TableCell>
                </TableRow>
                {open ? (
                  <TableRow>
                    <TableCell colSpan={colCount} className="bg-canvas-soft">
                      <div
                        className="space-y-3 py-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {showKColumns && atK.k != null ? (
                          <p className="text-xs text-mute">
                            Observational k metrics for this job (not PASS
                            authority; not identity). Display k=
                            <span className="font-mono">{atK.k}</span>
                            {nAtt != null ? (
                              <>
                                {" "}
                                · n_attempts=
                                <span className="font-mono">{nAtt}</span>
                              </>
                            ) : null}
                            . Sort remains Pass rate / Mean score.
                          </p>
                        ) : null}
                        <CodeBlock
                          path="profiles.yaml"
                          content={yamlText}
                          maxHeightClass="max-h-56"
                        />
                        <CodeBlock
                          path="rehydrate.sh"
                          content={rehydrateScript}
                          maxHeightClass="max-h-40"
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
