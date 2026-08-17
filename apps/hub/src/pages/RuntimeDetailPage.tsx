import { Check, Copy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { HoverTip, TruncateTip } from "@/components/hover-tip";
import {
  compareValues,
  nextSort,
  SortableHead,
  type SortDir,
} from "@/components/sortable-head";
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

const COL_MODEL = "min-w-0 overflow-hidden";
const COL_METRIC = "w-[7.5rem]";
const COL_DATASET = "w-[12rem] overflow-hidden";
const COL_ROLE = "w-[5rem]";
const COL_TEAM = "w-[7rem] overflow-hidden";
const COL_USER = "w-[6.5rem] overflow-hidden";
const COL_SUITE = "w-[6rem]";

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
  const [sortKey, setSortKey] = useState<string | null>("pass_rate");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
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

  const appearances = useMemo(() => {
    const rows = detail?.appearances ?? [];
    if (!sortKey || !sortDir) return rows;
    return [...rows].sort((a, b) => {
      const av = sortKey === "mean_score" ? a.mean_score : a.pass_rate;
      const bv = sortKey === "mean_score" ? b.mean_score : b.pass_rate;
      return compareValues(av, bv, sortDir);
    });
  }, [detail, sortKey, sortDir]);

  function onSort(key: string) {
    const next = nextSort(sortKey, sortDir, key);
    setSortKey(next.dir ? next.key : null);
    setSortDir(next.dir);
  }

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
          </div>

          <section>
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
            <h2 className="text-sm font-medium text-ink">Results</h2>
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={COL_MODEL}>Model</TableHead>
                    <TableHead className={`text-right ${COL_METRIC}`}>
                      <SortableHead
                        label="Pass rate"
                        active={sortKey === "pass_rate"}
                        dir={sortKey === "pass_rate" ? sortDir : null}
                        onClick={() => onSort("pass_rate")}
                        className="ml-auto"
                      />
                    </TableHead>
                    <TableHead className={`text-right ${COL_METRIC}`}>
                      <SortableHead
                        label="Mean score"
                        active={sortKey === "mean_score"}
                        dir={sortKey === "mean_score" ? sortDir : null}
                        onClick={() => onSort("mean_score")}
                        className="ml-auto"
                      />
                    </TableHead>
                    <TableHead className={COL_DATASET}>Dataset</TableHead>
                    <TableHead className={COL_ROLE}>Role</TableHead>
                    <TableHead className={COL_TEAM}>Teammates</TableHead>
                    <TableHead className={COL_USER}>Uploader</TableHead>
                    <TableHead className={COL_SUITE}>Suite run</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {appearances.map((row) => {
                    const href = `/datasets/${encodeDatasetId(row.database_id)}?tab=leaderboard&suite=${encodeURIComponent(row.suite_run_id)}`;
                    const teammates = row.teammates || [];
                    const suiteShort = shortSuiteId(row.suite_run_id);
                    return (
                      <TableRow
                        key={`${row.suite_run_id}:${row.role}`}
                      >
                        <TableCell className={COL_MODEL}>
                          <TruncateTip
                            text={row.model}
                            className="font-mono text-xs"
                          />
                        </TableCell>
                        <TableCell
                          className={`text-right tabular-nums text-xs ${COL_METRIC}`}
                        >
                          {row.pass_rate == null
                            ? "—"
                            : `${(Number(row.pass_rate) * 100).toFixed(1)}%`}
                        </TableCell>
                        <TableCell
                          className={`text-right tabular-nums text-xs ${COL_METRIC}`}
                        >
                          {formatScore(row.mean_score)}
                        </TableCell>
                        <TableCell className={COL_DATASET}>
                          <Link
                            to={href}
                            className="inline-block max-w-full hover:text-ink hover:underline underline-offset-2"
                          >
                            <TruncateTip
                              text={row.database_id}
                              className="font-mono text-xs"
                            />
                          </Link>
                        </TableCell>
                        <TableCell className={`font-mono text-xs text-body ${COL_ROLE}`}>
                          {row.role}
                        </TableCell>
                        <TableCell className={`text-xs text-body ${COL_TEAM}`}>
                          <TruncateTip
                            text={
                              teammates.length
                                ? teammates
                                    .map((t) => `${t.display_name} (${t.role})`)
                                    .join(", ")
                                : ""
                            }
                          />
                        </TableCell>
                        <TableCell className={`font-mono text-xs text-mute ${COL_USER}`}>
                          <TruncateTip
                            text={row.uploaded_by}
                            className="font-mono text-xs text-mute"
                          />
                        </TableCell>
                        <TableCell className={`font-mono text-xs text-mute ${COL_SUITE}`}>
                          {suiteShort === row.suite_run_id ? (
                            suiteShort
                          ) : (
                            <HoverTip content={row.suite_run_id}>
                              <span className="inline-block">{suiteShort}</span>
                            </HoverTip>
                          )}
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
