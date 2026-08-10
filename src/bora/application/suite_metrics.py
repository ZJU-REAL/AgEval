"""Suite-level metric aggregation from per-task / per-attempt evaluator Results.

Rules (MVP, fixed — not package-configurable):

- ``pass_rate`` = count(status == PASS) / n_tasks  (legacy, one row per task)
- ``mean_score`` = mean of per-task scores; missing / non-numeric / ERROR
  treated as **0.0** (Harbor-like default for absent reward)
- FAIL with numeric score keeps that score (typically 0.0)
- **No suite-level PASS** — PASS remains per-task evaluator authority only

Multi-attempt (#47):

- Always-k produces *n* independent Attempt samples per task.
- **pass@k** = unbiased estimator ``1 - C(n-c, k) / C(n, k)`` (Chen / Harbor).
- **pass^k** = ``(c/n)^k`` (all-k succeed; BORA addition, not Harbor).
- Suite / dataset score for a metric = **mean over tasks** that have enough
  samples for that k (tasks with ``n < k`` are omitted from that k's mean).
- These metrics are job summary only — **not** package identity / fingerprint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import comb
from typing import Any

# Documented default for absent scores (Harbor reward-missing → 0).
MISSING_SCORE_AS = 0.0


def _normalize_status(raw: object) -> str:
    return str(raw or "").strip().upper()


def _numeric_score_or_none(raw: object) -> float | None:
    """Return a real number score, or None if missing / bool / non-numeric.

    ``bool`` is a subclass of ``int`` in Python; treat it as non-numeric so
    ``True``/``False`` never become 1.0/0.0 by accident.
    """
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return float(raw)


def _score_value(row: Mapping[str, Any]) -> float:
    """Per-task score contribution for mean_score.

    Missing / non-numeric → ``MISSING_SCORE_AS`` (0.0).
    Status ERROR also forces 0.0 even if a score field is present.
    """
    status = _normalize_status(row.get("status"))
    if status == "ERROR":
        return MISSING_SCORE_AS
    value = _numeric_score_or_none(row.get("score"))
    return MISSING_SCORE_AS if value is None else value


def aggregate_task_metrics(task_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate per-task result rows into stable suite metrics.

    Parameters
    ----------
    task_rows:
        Rows shaped like suite summary ``tasks[]`` entries
        (at least ``status``; optional ``score``).

    Returns
    -------
    dict
        ``pass_rate``, ``mean_score``, ``n_tasks``, ``n_pass``,
        ``n_fail``, ``n_error``, ``missing_score_as``.
    """
    n = len(task_rows)
    n_pass = 0
    n_fail = 0
    n_error = 0
    scores: list[float] = []

    for row in task_rows:
        st = _normalize_status(row.get("status"))
        if st == "PASS":
            n_pass += 1
        elif st == "FAIL":
            n_fail += 1
        else:
            # ERROR, SKIPPED, unknown → error bucket for rates; score → 0
            n_error += 1
        scores.append(_score_value(row))

    pass_rate = (n_pass / n) if n else 0.0
    mean_score = (sum(scores) / n) if n else 0.0

    return {
        "pass_rate": pass_rate,
        "mean_score": mean_score,
        "n_tasks": n,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_error": n_error,
        "missing_score_as": MISSING_SCORE_AS,
    }


def task_refs_for_summary(task_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Minimal per-task references for suite/job result rows (leaderboard)."""
    refs: list[dict[str, Any]] = []
    for row in task_rows:
        ref: dict[str, Any] = {
            "task_id": row.get("task_id"),
            "status": _normalize_status(row.get("status")) or None,
            "score": _numeric_score_or_none(row.get("score")),
            "run_id": row.get("run_id"),
        }
        if row.get("n") is not None:
            ref["n"] = row.get("n")
        if row.get("c") is not None:
            ref["c"] = row.get("c")
        refs.append(ref)
    return refs


# ---------------------------------------------------------------------------
# Multi-attempt: pass@k / pass^k (#47)
# ---------------------------------------------------------------------------


def pass_at_k(*, n: int, c: int, k: int) -> float | None:
    """Unbiased pass@k estimator (Chen et al.; Harbor).

    ``1 - C(n-c, k) / C(n, k)`` when ``n >= k``; else ``None`` (incomplete).
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return None
    if not isinstance(c, int) or isinstance(c, bool) or c < 0 or c > n:
        return None
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        return None
    if n < k:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - (comb(n - c, k) / comb(n, k))


def pass_power_k(*, n: int, c: int, k: int) -> float | None:
    """pass^k estimator: probability all *k* independent attempts succeed.

    Uses ``(c/n)^k``. Returns ``None`` when ``n < 1`` or *k* invalid.
    Does not require ``n >= k`` (with Always-k, n is usually the sample budget).
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        return None
    if not isinstance(c, int) or isinstance(c, bool) or c < 0 or c > n:
        return None
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        return None
    return (c / n) ** k


def default_k_values(n_samples: int) -> list[int]:
    """Harbor-like k set: 1, powers of 2, steps of 5, and *n_samples* itself."""
    if not isinstance(n_samples, int) or isinstance(n_samples, bool) or n_samples < 1:
        return []
    ks: set[int] = {1, n_samples}
    p = 2
    while p <= n_samples:
        ks.add(p)
        p *= 2
    for m in range(5, n_samples + 1, 5):
        ks.add(m)
    return sorted(ks)


def count_passes(attempt_rows: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    """Return ``(n, c)`` where *c* counts attempts with status PASS."""
    n = len(attempt_rows)
    c = sum(1 for row in attempt_rows if _normalize_status(row.get("status")) == "PASS")
    return n, c


def group_attempts_by_task(
    attempt_rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Group attempt rows by ``task_id`` (stable insertion order of first seen)."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in attempt_rows:
        tid = str(row.get("task_id") or "")
        if tid not in groups:
            groups[tid] = []
        groups[tid].append(row)
    return groups


def _metrics_map_for_nc(
    n: int,
    c: int,
    k_values: Sequence[int],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    pass_at: dict[str, float | None] = {}
    pass_pow: dict[str, float | None] = {}
    for k in k_values:
        key = str(k)
        pass_at[key] = pass_at_k(n=n, c=c, k=k)
        pass_pow[key] = pass_power_k(n=n, c=c, k=k)
    return pass_at, pass_pow


def rollup_task_from_attempts(
    task_id: str,
    attempt_rows: Sequence[Mapping[str, Any]],
    *,
    k_values: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Collapse attempt samples for one task into a summary row + k-metrics."""
    ordered = sorted(
        attempt_rows,
        key=lambda r: (
            int(r["attempt_index"])
            if isinstance(r.get("attempt_index"), int)
            and not isinstance(r.get("attempt_index"), bool)
            else 10**9,
            str(r.get("run_id") or ""),
        ),
    )
    n, c = count_passes(ordered)
    ks = list(k_values) if k_values is not None else default_k_values(n if n else 1)
    pass_at, pass_pow = _metrics_map_for_nc(n, c, ks)

    # Rolled status: any PASS → PASS; else any FAIL → FAIL; else ERROR.
    statuses = [_normalize_status(r.get("status")) for r in ordered]
    if any(s == "PASS" for s in statuses):
        status = "PASS"
    elif any(s == "FAIL" for s in statuses):
        status = "FAIL"
    elif any(s == "ERROR" for s in statuses) or not statuses:
        status = "ERROR"
    else:
        status = statuses[-1]

    # Representative score: mean of attempt scores (ERROR→0), Harbor-like.
    scores = [_score_value(r) for r in ordered]
    mean_score = (sum(scores) / len(scores)) if scores else MISSING_SCORE_AS
    # Prefer a PASS attempt's run_id for task_refs; else first.
    run_id = None
    for r in ordered:
        if _normalize_status(r.get("status")) == "PASS" and r.get("run_id"):
            run_id = r.get("run_id")
            break
    if run_id is None and ordered:
        run_id = ordered[0].get("run_id")

    return {
        "task_id": task_id,
        "status": status,
        "score": mean_score,
        "n": n,
        "c": c,
        "run_id": run_id,
        "attempt_indices": [
            r.get("attempt_index") for r in ordered if r.get("attempt_index") is not None
        ],
        "pass_at_k": pass_at,
        "pass_power_k": pass_pow,
        "attempts": list(ordered),
    }


def aggregate_k_metrics(
    attempt_rows: Sequence[Mapping[str, Any]],
    *,
    task_ids: Sequence[str] | None = None,
    n_attempts: int | None = None,
    k_values: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Compute per-task and suite-mean pass@k / pass^k from attempt samples.

    Tasks with ``n < k`` are **omitted** from that *k*'s suite mean (incomplete).
    Metrics never enter ``config_fingerprint`` — caller places them under
    ``metrics`` / job summary only.
    """
    groups = group_attempts_by_task(attempt_rows)
    ordered_ids: list[str]
    if task_ids is not None:
        ordered_ids = [str(t) for t in task_ids]
        for tid in groups:
            if tid not in ordered_ids:
                ordered_ids.append(tid)
    else:
        ordered_ids = list(groups.keys())

    sample_budget = n_attempts
    if sample_budget is None:
        sample_budget = max((len(groups[t]) for t in ordered_ids if t in groups), default=1)
    if sample_budget < 1:
        sample_budget = 1

    ks = list(k_values) if k_values is not None else default_k_values(sample_budget)

    task_rows: list[dict[str, Any]] = []
    for tid in ordered_ids:
        rows = groups.get(tid, [])
        task_rows.append(rollup_task_from_attempts(tid, rows, k_values=ks))

    # Suite mean per k: mean over tasks where the value is not None.
    suite_pass_at: dict[str, Any] = {}
    suite_pass_pow: dict[str, Any] = {}
    for k in ks:
        key = str(k)
        at_vals = [
            float(t["pass_at_k"][key])
            for t in task_rows
            if t.get("pass_at_k", {}).get(key) is not None
        ]
        pow_vals = [
            float(t["pass_power_k"][key])
            for t in task_rows
            if t.get("pass_power_k", {}).get(key) is not None
        ]
        suite_pass_at[key] = {
            "value": (sum(at_vals) / len(at_vals)) if at_vals else None,
            "n_tasks": len(at_vals),
            "incomplete_tasks": len(task_rows) - len(at_vals),
        }
        suite_pass_pow[key] = {
            "value": (sum(pow_vals) / len(pow_vals)) if pow_vals else None,
            "n_tasks": len(pow_vals),
            "incomplete_tasks": len(task_rows) - len(pow_vals),
        }

    legacy = aggregate_task_metrics(task_rows)
    return {
        **legacy,
        "n_attempts": sample_budget,
        "k_values": list(ks),
        "pass_at_k": suite_pass_at,
        "pass_power_k": suite_pass_pow,
        "per_task": [
            {
                "task_id": t["task_id"],
                "n": t["n"],
                "c": t["c"],
                "status": t["status"],
                "pass_at_k": t["pass_at_k"],
                "pass_power_k": t["pass_power_k"],
            }
            for t in task_rows
        ],
        "task_rows": task_rows,
    }


def flatten_legacy_tasks_as_attempts(
    task_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert pre-#47 summary ``tasks[]`` (one row per task) into attempt rows."""
    out: list[dict[str, Any]] = []
    for row in task_rows:
        # Already multi-attempt nested?
        nested = row.get("attempts")
        if isinstance(nested, list) and nested:
            for a in nested:
                if isinstance(a, Mapping):
                    out.append(dict(a))
            continue
        attempt_index = row.get("attempt_index")
        if not isinstance(attempt_index, int) or isinstance(attempt_index, bool):
            attempt_index = 0
        out.append(
            {
                "task_id": row.get("task_id"),
                "attempt_index": attempt_index,
                "exit_code": row.get("exit_code"),
                "status": row.get("status"),
                "score": row.get("score"),
                "metrics": row.get("metrics") if isinstance(row.get("metrics"), dict) else {},
                "run_id": row.get("run_id"),
                "digest": row.get("digest"),
                "error": row.get("error"),
            }
        )
    return out
