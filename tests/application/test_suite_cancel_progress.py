"""Suite cancel + progress callback (#47 D3/D4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from bora.application.suite_run import (
    _existing_attempt_keys,
    execute_suite_run,
    is_suite_cancel_requested,
    plan_suite_run,
    request_suite_cancel,
)

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


@pytest.mark.asyncio
async def test_cancel_stops_new_units() -> None:
    plan = plan_suite_run(SUITE, n_attempts=1, max_concurrent_tasks=1)
    plan.task_ids = ["alpha", "beta", "gamma"]
    calls: list[str] = []

    async def runner(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        calls.append(task_id)
        if task_id == "alpha":
            # After first unit starts, request cancel so remaining are not run.
            request_suite_cancel(plan.database_root, plan.suite_run_id)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.02)
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path=None, logs=None)
        return 0, result, {"digest": f"sha256:{task_id}"}

    summary = await execute_suite_run(plan, run_fn=runner)
    assert summary.get("cancelled") is True
    assert is_suite_cancel_requested(plan.database_root, plan.suite_run_id)
    # At most alpha fully ran; beta/gamma cancelled (or not started as real runs).
    assert "alpha" in calls
    assert len(calls) < 3
    cancelled_rows = [a for a in summary["attempts"] if a.get("phase") == "cancelled"]
    assert cancelled_rows
    assert all(r.get("error") == "suite_cancelled" for r in cancelled_rows)


def test_existing_keys_skip_cancelled_placeholders() -> None:
    rows = [
        {"task_id": "alpha", "attempt_index": 0, "status": "PASS", "run_id": "r0"},
        {
            "task_id": "alpha",
            "attempt_index": 1,
            "status": "ERROR",
            "phase": "cancelled",
            "error": "suite_cancelled",
            "run_id": None,
        },
        {
            "task_id": "beta",
            "attempt_index": 0,
            "status": "ERROR",
            "error": "suite_cancelled",
            "run_id": None,
        },
    ]
    assert _existing_attempt_keys(rows) == {("alpha", 0)}


@pytest.mark.asyncio
async def test_resume_retries_cancelled_placeholders() -> None:
    """Cancel mid-suite → resume must re-run cancelled slots (not deflate pass@k)."""
    plan = plan_suite_run(SUITE, n_attempts=1, max_concurrent_tasks=1)
    plan.task_ids = ["alpha", "beta", "gamma"]
    first_calls: list[str] = []

    async def runner1(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        first_calls.append(task_id)
        if task_id == "alpha":
            request_suite_cancel(plan.database_root, plan.suite_run_id)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.02)
        run_id = f"sha256_dead_run_{task_id}_1"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        result = SimpleNamespace(
            status="PASS",
            score=1.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        return 0, result, {"digest": f"sha256:{task_id}", "run_dir": str(abs_run)}

    first = await execute_suite_run(plan, run_fn=runner1)
    assert first.get("cancelled") is True
    suite_id = first["suite_run_id"]
    cancelled = [a for a in first["attempts"] if a.get("phase") == "cancelled"]
    assert cancelled
    assert is_suite_cancel_requested(plan.database_root, suite_id)

    plan2 = plan_suite_run(
        SUITE,
        n_attempts=1,
        max_concurrent_tasks=1,
        suite_run_id=suite_id,
    )
    plan2.task_ids = ["alpha", "beta", "gamma"]
    second_calls: list[str] = []

    async def runner2(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        second_calls.append(task_id)
        run_id = f"sha256_dead_run_{task_id}_2"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        result = SimpleNamespace(
            status="PASS",
            score=1.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        return 0, result, {"digest": f"sha256:{task_id}2", "run_dir": str(abs_run)}

    second = await execute_suite_run(plan2, run_fn=runner2, resume=True)
    assert second.get("resumed") is True
    # Cancel file cleared so scheduling works again.
    assert not is_suite_cancel_requested(plan.database_root, suite_id)
    # Cancelled slots re-ran; finished alpha not re-run.
    assert "alpha" not in second_calls
    assert (
        set(second_calls) >= {c for c in ["beta", "gamma"] if c not in first_calls} or second_calls
    )
    # Prefer: every cancelled task_id appears in second_calls
    cancelled_tids = {a["task_id"] for a in cancelled}
    assert cancelled_tids <= set(second_calls)
    # No leftover cancelled placeholders for completed k=1 suite
    leftover = [a for a in second["attempts"] if a.get("phase") == "cancelled"]
    assert leftover == []
    assert len(second["attempts"]) == 3
    assert all(a.get("status") == "PASS" for a in second["attempts"])
    assert second["metrics"]["pass_rate"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_progress_callback_events() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=2, max_concurrent_tasks=1)
    events: list[str] = []

    async def runner(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path=None, logs=None)
        return 0, result, {"digest": "sha256:x"}

    def on_progress(ev: dict) -> None:
        events.append(str(ev.get("type")))

    summary = await execute_suite_run(plan, run_fn=runner, on_progress=on_progress)
    assert summary["n_attempts"] == 2
    assert "suite_start" in events
    assert events.count("unit_start") == 2
    assert events.count("unit_done") == 2
    assert "suite_complete" in events
    prog = Path(summary["summary_path"]).parent / "progress.json"
    assert prog.is_file()
