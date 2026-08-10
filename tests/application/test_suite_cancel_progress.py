"""Suite cancel + progress callback (#47 D3/D4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from bora.application.suite_run import (
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
