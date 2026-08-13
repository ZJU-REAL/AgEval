"""Pre-upload ensure/recompute of pass@k metrics (#60 A)."""

from __future__ import annotations

import pytest

from bora.application.suite.suite_metrics import (
    ensure_suite_metrics,
    ensure_suite_task_refs,
    has_k_metrics,
    task_refs_for_summary,
)


def test_has_k_metrics() -> None:
    assert not has_k_metrics(None)
    assert not has_k_metrics({})
    assert not has_k_metrics({"pass_at_k": {"1": {"value": 1.0}}})
    assert has_k_metrics(
        {
            "pass_at_k": {"1": {"value": 1.0, "n_tasks": 1, "incomplete_tasks": 0}},
            "pass_power_k": {"1": {"value": 1.0, "n_tasks": 1, "incomplete_tasks": 0}},
        }
    )


def test_recompute_pass_at_k_from_attempts_when_metrics_missing() -> None:
    summary = {
        "n_attempts": 2,
        "task_ids": ["a", "b"],
        "attempts": [
            {"task_id": "a", "attempt_index": 0, "status": "PASS", "run_id": "a0"},
            {"task_id": "a", "attempt_index": 1, "status": "PASS", "run_id": "a1"},
            {"task_id": "b", "attempt_index": 0, "status": "FAIL", "run_id": "b0"},
            {"task_id": "b", "attempt_index": 1, "status": "FAIL", "run_id": "b1"},
        ],
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "n": 2, "c": 2, "run_id": "a0"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "n": 2, "c": 0, "run_id": "b0"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert has_k_metrics(m)
    assert m["n_attempts"] == 2
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.5)
    assert m["pass_at_k"]["2"]["value"] == pytest.approx(0.5)
    assert m["pass_power_k"]["2"]["value"] == pytest.approx(0.5)
    assert m["pass_rate"] == pytest.approx(0.5)
    assert isinstance(m["per_task"], list) and len(m["per_task"]) == 2
    assert m["k_values"] == [1, 2]


def test_recompute_from_task_n_c_without_attempts() -> None:
    summary = {
        "n_attempts": 3,
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 0.4, "n": 3, "c": 2, "run_id": "r1"},
            {"task_id": "b", "status": "FAIL", "score": 0.1, "n": 3, "c": 0, "run_id": "r2"},
        ],
        # metrics present but only legacy keys (no pass@k); mean_score is partial credit
        "metrics": {
            "pass_rate": 0.5,
            "mean_score": 0.25,
            "n_tasks": 2,
            "n_pass": 1,
            "n_fail": 1,
            "n_error": 0,
            "missing_score_as": 0.0,
        },
    }
    m = ensure_suite_metrics(summary)
    assert has_k_metrics(m)
    assert m["n_attempts"] == 3
    # a: pass@1 = 2/3, b: 0 → mean 1/3
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(1 / 3)
    assert "3" in m["pass_at_k"]
    # Synthetic n/c must not overwrite real mean_score / pass_rate with 0/1 scores
    assert m["mean_score"] == pytest.approx(0.25)
    assert m["pass_rate"] == pytest.approx(0.5)
    assert m["n_tasks"] == 2


def test_keep_existing_k_metrics_without_overwrite() -> None:
    summary = {
        "metrics": {
            "pass_rate": 1.0,
            "mean_score": 1.0,
            "n_tasks": 1,
            "n_pass": 1,
            "n_fail": 0,
            "n_error": 0,
            "missing_score_as": 0.0,
            "n_attempts": 4,
            "k_values": [1, 2, 4],
            "pass_at_k": {
                "1": {"value": 0.9, "n_tasks": 1, "incomplete_tasks": 0},
                "4": {"value": 0.75, "n_tasks": 1, "incomplete_tasks": 0},
            },
            "pass_power_k": {
                "1": {"value": 0.9, "n_tasks": 1, "incomplete_tasks": 0},
                "4": {"value": 0.5, "n_tasks": 1, "incomplete_tasks": 0},
            },
            "per_task": [{"task_id": "a", "n": 4, "c": 3}],
        },
        "attempts": [
            # Would yield different numbers if recomputed — must not recompute.
            {"task_id": "a", "attempt_index": 0, "status": "FAIL"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.9)
    assert m["pass_at_k"]["4"]["value"] == pytest.approx(0.75)
    assert m["n_attempts"] == 4


def test_legacy_tasks_only_gets_pass_rate_and_k1() -> None:
    """No n/c and no attempts[] → still get k maps from single-sample flatten."""
    summary = {
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "r1"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "run_id": "r2"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert m["pass_rate"] == pytest.approx(0.5)
    assert has_k_metrics(m)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.5)
    assert m["n_attempts"] == 1


def test_n_without_c_pass_does_not_invent_perfect_multi_attempt() -> None:
    """Rolled PASS + n without c must not synthesize c=n (pass@k inflation)."""
    summary = {
        "n_attempts": 4,
        "tasks": [
            # Would be catastrophic if c were invented as 4.
            {"task_id": "a", "status": "PASS", "score": 1.0, "n": 4, "run_id": "a0"},
        ],
    }
    m = ensure_suite_metrics(summary)
    # Single-sample fallback: pass@1 from rolled status only.
    assert has_k_metrics(m)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(1.0)
    # Multi-k must not claim a perfect Always-4 pass.
    assert m["pass_at_k"].get("4") is None or m["pass_at_k"]["4"]["value"] is None
    per = {str(t["task_id"]): t for t in m.get("per_task") or []}
    assert per["a"]["n"] == 1  # not fabricated n=4
    assert per["a"]["c"] == 1


def test_n_without_c_fail_recovers_zero_passes() -> None:
    """Rolled FAIL + n without c ⇒ c=0 under BORA rollup (no PASS existed)."""
    summary = {
        "n_attempts": 3,
        "tasks": [
            {"task_id": "a", "status": "FAIL", "score": 0.0, "n": 3, "run_id": "a0"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert has_k_metrics(m)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.0)
    assert m["pass_at_k"]["3"]["value"] == pytest.approx(0.0)
    per = {str(t["task_id"]): t for t in m.get("per_task") or []}
    assert per["a"]["n"] == 3
    assert per["a"]["c"] == 0


def test_n_equals_1_without_c_uses_rolled_status() -> None:
    summary = {
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "n": 1, "run_id": "a0"},
            {"task_id": "b", "status": "FAIL", "score": 0.0, "n": 1, "run_id": "b0"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.5)
    per = {str(t["task_id"]): t for t in m.get("per_task") or []}
    assert per["a"]["n"] == 1 and per["a"]["c"] == 1
    assert per["b"]["n"] == 1 and per["b"]["c"] == 0


def test_mixed_full_nc_and_n_without_c_pass() -> None:
    """Recoverable n/c stays multi-attempt; incomplete PASS stays single-sample."""
    summary = {
        "n_attempts": 4,
        "tasks": [
            {"task_id": "full", "status": "PASS", "score": 1.0, "n": 4, "c": 2, "run_id": "f0"},
            {"task_id": "partial", "status": "PASS", "score": 1.0, "n": 4, "run_id": "p0"},
        ],
    }
    m = ensure_suite_metrics(summary)
    assert has_k_metrics(m)
    per = {str(t["task_id"]): t for t in m.get("per_task") or []}
    assert per["full"]["n"] == 4 and per["full"]["c"] == 2
    assert per["partial"]["n"] == 1 and per["partial"]["c"] == 1
    # pass@4: only ``full`` has n>=4; unbiased pass@4 for n=4,c=2 = 1 - C(2,4)/C(4,4)
    # C(2,4)=0 so pass@4 = 1.0 for full; partial incomplete → mean over 1 task.
    assert m["pass_at_k"]["4"]["n_tasks"] == 1
    assert m["pass_at_k"]["4"]["incomplete_tasks"] == 1
    assert m["pass_at_k"]["4"]["value"] == pytest.approx(1.0)


def test_task_refs_include_n_c_and_attempt_run_ids() -> None:
    tasks = [
        {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "a0"},
        {"task_id": "b", "status": "FAIL", "score": 0.0, "run_id": "b0"},
    ]
    attempts = [
        {"task_id": "a", "attempt_index": 0, "status": "PASS", "run_id": "a0"},
        {"task_id": "a", "attempt_index": 1, "status": "FAIL", "run_id": "a1"},
        {"task_id": "b", "attempt_index": 0, "status": "FAIL", "run_id": "b0"},
        {"task_id": "b", "attempt_index": 1, "status": "FAIL", "run_id": "b1"},
    ]
    refs = task_refs_for_summary(tasks, attempts=attempts)
    by_id = {str(r["task_id"]): r for r in refs}
    assert by_id["a"]["n"] == 2
    assert by_id["a"]["c"] == 1
    assert by_id["a"]["attempt_run_ids"] == ["a0", "a1"]
    assert by_id["b"]["n"] == 2
    assert by_id["b"]["c"] == 0
    assert by_id["b"]["attempt_run_ids"] == ["b0", "b1"]


def test_ensure_suite_task_refs_from_summary_attempts() -> None:
    summary = {
        "tasks": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "n": 2, "c": 2, "run_id": "a0"},
        ],
        "attempts": [
            {"task_id": "a", "attempt_index": 0, "status": "PASS", "run_id": "a0"},
            {"task_id": "a", "attempt_index": 1, "status": "PASS", "run_id": "a1"},
        ],
        "task_refs": [
            {"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "a0"},
        ],
    }
    refs = ensure_suite_task_refs(summary)
    assert len(refs) == 1
    assert refs[0]["n"] == 2
    assert refs[0]["c"] == 2
    assert refs[0]["attempt_run_ids"] == ["a0", "a1"]
