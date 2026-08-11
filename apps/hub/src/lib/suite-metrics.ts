/**
 * Observational suite metrics helpers for Hub Leaderboard (#60).
 * pass@k / pass^k are job aggregates — never suite PASS.
 */

export type KMetricCell = {
  value: number | null;
  n_tasks?: number;
  incomplete_tasks?: number;
};

export type KMetricMap = Record<string, KMetricCell | number | null | undefined>;

/** Read metrics.n_attempts when present (CLI/job budget only). */
export function metricsNAttempts(
  metrics: Record<string, unknown> | null | undefined,
): number | null {
  if (!metrics) return null;
  const raw = metrics.n_attempts;
  if (typeof raw === "number" && Number.isFinite(raw) && raw >= 1) return raw;
  return null;
}

/**
 * Primary display k for Leaderboard columns.
 * Prefer max(k_values) or max key in pass_at_k; fall back to n_attempts; else null.
 */
export function primaryDisplayK(
  metrics: Record<string, unknown> | null | undefined,
): number | null {
  if (!metrics) return null;
  const keys = kKeysFromMetrics(metrics);
  if (keys.length) return keys[keys.length - 1]!;
  return metricsNAttempts(metrics);
}

function kKeysFromMetrics(metrics: Record<string, unknown>): number[] {
  const fromList = metrics.k_values;
  if (Array.isArray(fromList) && fromList.length) {
    const nums = fromList
      .map((x) => (typeof x === "number" ? x : Number(x)))
      .filter((n) => Number.isFinite(n) && n >= 1) as number[];
    if (nums.length) return [...new Set(nums)].sort((a, b) => a - b);
  }
  const passAt = metrics.pass_at_k;
  if (passAt && typeof passAt === "object" && !Array.isArray(passAt)) {
    const nums = Object.keys(passAt as object)
      .map((k) => Number(k))
      .filter((n) => Number.isFinite(n) && n >= 1);
    if (nums.length) return [...new Set(nums)].sort((a, b) => a - b);
  }
  return [];
}

function cellValue(raw: unknown): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) ? raw : null;
  }
  if (typeof raw === "object" && raw !== null && "value" in raw) {
    const v = (raw as KMetricCell).value;
    if (v == null) return null;
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

/** Value of pass@k or pass^k for a specific k (string or number key). */
export function metricAtK(
  map: unknown,
  k: number | null,
): number | null {
  if (k == null || map == null || typeof map !== "object") return null;
  const rec = map as KMetricMap;
  const raw = rec[String(k)] ?? rec[k as unknown as string];
  return cellValue(raw);
}

/** pass@k for the primary display k; null → show "—". */
export function passAtPrimaryK(
  metrics: Record<string, unknown> | null | undefined,
): { k: number | null; value: number | null } {
  const k = primaryDisplayK(metrics);
  if (!metrics || k == null) return { k, value: null };
  return { k, value: metricAtK(metrics.pass_at_k, k) };
}

/** pass^k for the primary display k. */
export function passPowerPrimaryK(
  metrics: Record<string, unknown> | null | undefined,
): { k: number | null; value: number | null } {
  const k = primaryDisplayK(metrics);
  if (!metrics || k == null) return { k, value: null };
  return { k, value: metricAtK(metrics.pass_power_k, k) };
}

/** Format rate-like metric as percent, or em dash when absent. */
export function formatPassMetric(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}
