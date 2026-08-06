"""Suite-level metric aggregation from per-task evaluator Results.

Rules (MVP, fixed — not package-configurable):

- ``pass_rate`` = count(status == PASS) / n_tasks
- ``mean_score`` = mean of per-task scores; missing / non-numeric / ERROR
  treated as **0.0** (Harbor-like default for absent reward)
- FAIL with numeric score keeps that score (typically 0.0)
- **No suite-level PASS** — PASS remains per-task evaluator authority only

These fields are observational aggregates for leaderboard / ops summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
        refs.append(
            {
                "task_id": row.get("task_id"),
                "status": _normalize_status(row.get("status")) or None,
                "score": _numeric_score_or_none(row.get("score")),
                "run_id": row.get("run_id"),
            }
        )
    return refs
