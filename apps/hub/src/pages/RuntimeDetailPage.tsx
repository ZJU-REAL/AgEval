import { Check, Copy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  encodeDatasetId,
  getRuntime,
  RegistryHttpError,
  type RuntimeDetail,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { CodeHighlight } from "@/lib/code-highlight";
import { formatScore } from "@/lib/utils";

function harnessYaml(card: RuntimeDetail): string {
  const lines = [`executor: ${card.executor || '""'}`, `entry: ${card.entry || '""'}`, "options:"];
  const keys = Object.keys(card.options || {}).sort();
  if (!keys.length) {
    lines.push("  {}");
  } else {
    for (const key of keys) {
      const val = card.options[key];
      lines.push(
        `  ${key}: ${typeof val === "string" ? val : JSON.stringify(val)}`,
      );
    }
  }
  return `${lines.join("\n")}\n`;
}

function shortSuiteId(id: string): string {
  const raw = id.trim();
  if (raw.length <= 12) return raw;
  return `${raw.slice(0, 10)}…`;
}

export function RuntimeDetailPage() {
  const { runtimeId: rawId } = useParams();
  const runtimeId = decodeURIComponent(rawId || "");
  const [detail, setDetail] = useState<RuntimeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const token = getToken();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRuntime(runtimeId, token)
      .then((row) => {
        if (cancelled) return;
        setDetail(row);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runtimeId, token]);

  const yamlText = useMemo(() => (detail ? harnessYaml(detail) : ""), [detail]);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(yamlText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  return (
    <>
      <BreadcrumbNav
        items={[
          { label: "Runtimes", href: "/runtimes" },
          { label: detail?.display_name || runtimeId || "…" },
        ]}
        className="mb-4"
      />

      {loading ? <p className="text-sm text-mute">Loading…</p> : null}
      {error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load runtime</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
          <p className="mt-3">
            <Link to="/runtimes" className="underline underline-offset-2 text-body">
              ← Back to runtimes
            </Link>
          </p>
        </div>
      ) : null}

      {!loading && !error && detail ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-ink">
              {detail.display_name}
            </h1>
            <p className="text-sm text-mute mt-1 font-mono">{detail.runtime_id}</p>
            <p className="text-xs text-mute mt-2">
              Appearance scores are the source suite board metrics — not a
              Runtime index and not suite PASS.
            </p>
          </div>

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Harness</h2>
            <div className="relative rounded-[6px] border border-hairline bg-code-bg">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => void onCopy()}
                aria-label="Copy"
                className="absolute right-1.5 top-1.5 z-10 h-7 w-7 shrink-0"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-ink" />
                ) : (
                  <Copy className="h-3.5 w-3.5 text-mute" />
                )}
              </Button>
              <pre className="m-0 overflow-auto p-3 pr-10 font-mono text-[12px] leading-5 whitespace-pre max-h-56">
                <code>
                  <CodeHighlight path="harness.yaml" content={yamlText} />
                </code>
              </pre>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Appearances</h2>
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Dataset</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Pass rate</TableHead>
                    <TableHead className="text-right">Mean score</TableHead>
                    <TableHead>Teammates</TableHead>
                    <TableHead>Uploader</TableHead>
                    <TableHead>Suite run</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.appearances.map((row) => {
                    const href = `/datasets/${encodeDatasetId(row.database_id)}?tab=leaderboard&suite=${encodeURIComponent(row.suite_run_id)}`;
                    const teammates = row.teammates || [];
                    return (
                      <TableRow
                        key={`${row.suite_run_id}:${row.role}`}
                      >
                        <TableCell className="font-mono text-xs">
                          <Link
                            to={href}
                            className="hover:text-ink hover:underline underline-offset-2"
                          >
                            {row.database_id}
                          </Link>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-body">
                          {row.role}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-body">
                          {row.model || "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-xs">
                          {row.pass_rate == null
                            ? "—"
                            : `${(Number(row.pass_rate) * 100).toFixed(1)}%`}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-xs">
                          {formatScore(row.mean_score)}
                        </TableCell>
                        <TableCell className="text-xs text-body">
                          {teammates.length
                            ? teammates
                                .map((t) => `${t.display_name} (${t.role})`)
                                .join(", ")
                            : "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-mute">
                          {row.uploaded_by || "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-mute" title={row.suite_run_id}>
                          {shortSuiteId(row.suite_run_id)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
