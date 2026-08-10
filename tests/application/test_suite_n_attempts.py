"""Always-k suite orchestration + resume (#47 A/C)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bora.application.suite_run import (
    execute_suite_run,
    get_inflight_peak,
    plan_suite_run,
    planned_units,
    reset_inflight_metrics,
)
from bora.config.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def test_plan_n_attempts_default_and_reject() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha")
    assert plan.n_attempts == 1
    assert planned_units(plan) == [("alpha", 0)]

    plan3 = plan_suite_run(SUITE, task_id="alpha", n_attempts=3, max_concurrent_tasks=2)
    assert plan3.n_attempts == 3
    assert plan3.max_concurrent_tasks == 2  # multi-attempt may parallelize
    assert planned_units(plan3) == [("alpha", 0), ("alpha", 1), ("alpha", 2)]

    with pytest.raises(ConfigError):
        plan_suite_run(SUITE, n_attempts=0)


def test_plan_single_task_k1_forces_concurrency_1() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", max_concurrent_tasks=8, n_attempts=1)
    assert plan.max_concurrent_tasks == 1


@pytest.mark.asyncio
async def test_always_k_produces_k_attempts() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=3, max_concurrent_tasks=1)
    calls: list[str] = []

    async def runner(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        calls.append(task_id)
        run_id = f"sha256_dead_run_{task_id}_{len(calls)}"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        # 2 pass, 1 fail across 3 calls
        status = "PASS" if len(calls) <= 2 else "FAIL"
        result = SimpleNamespace(
            status=status,
            score=1.0 if status == "PASS" else 0.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        code = 0 if status == "PASS" else 1
        return code, result, {"digest": "sha256:x", "run_dir": str(abs_run)}

    summary = await execute_suite_run(plan, run_fn=runner)
    assert len(calls) == 3
    assert summary["n_attempts"] == 3
    assert len(summary["attempts"]) == 3
    assert {a["attempt_index"] for a in summary["attempts"]} == {0, 1, 2}
    assert summary["tasks"][0]["n"] == 3
    assert summary["tasks"][0]["c"] == 2
    # pass@1 ≈ 2/3; pass@3 = 1 (at least one pass when n=k and c>0 → wait
    # unbiased with n=3,c=2,k=3: n-c=1 < 3 → 1.0
    assert summary["metrics"]["pass_at_k"]["3"]["value"] == pytest.approx(1.0)
    assert summary["metrics"]["pass_at_k"]["1"]["value"] == pytest.approx(2 / 3)
    # pass^k: (2/3)^3
    assert summary["metrics"]["pass_power_k"]["3"]["value"] == pytest.approx((2 / 3) ** 3)
    # k-metrics must not appear as fingerprint inputs
    assert "n_attempts" not in str(summary["config_fingerprint"])
    path = Path(summary["summary_path"])
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert disk["n_attempts"] == 3
    assert len(disk["attempts"]) == 3


@pytest.mark.asyncio
async def test_parallel_does_not_change_k() -> None:
    plan = plan_suite_run(
        SUITE,
        task_id="alpha",
        n_attempts=4,
        max_concurrent_tasks=2,
    )
    reset_inflight_metrics()

    async def slow(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        await asyncio.sleep(0.08)
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path=None, logs=None)
        return 0, result, {"digest": "sha256:x"}

    summary = await execute_suite_run(plan, run_fn=slow)
    assert len(summary["attempts"]) == 4
    assert summary["n_attempts"] == 4
    assert get_inflight_peak() <= 2
    assert get_inflight_peak() >= 2  # actually exercised concurrency


@pytest.mark.asyncio
async def test_resume_skips_completed_and_appends() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=2, max_concurrent_tasks=1)
    call_n = {"n": 0}

    async def runner(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        call_n["n"] += 1
        i = call_n["n"]
        run_id = f"sha256_dead_run_alpha_{i}"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        result = SimpleNamespace(
            status="PASS",
            score=1.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        return 0, result, {"digest": f"sha256:{i}", "run_dir": str(abs_run)}

    first = await execute_suite_run(plan, run_fn=runner)
    assert len(first["attempts"]) == 2
    assert call_n["n"] == 2
    suite_id = first["suite_run_id"]
    first_run_ids = {a["run_id"] for a in first["attempts"]}

    # Resume with higher k → only new indices run
    plan2 = plan_suite_run(
        SUITE,
        task_id="alpha",
        n_attempts=4,
        max_concurrent_tasks=1,
        suite_run_id=suite_id,
    )
    second = await execute_suite_run(plan2, run_fn=runner, resume=True)
    assert second["resumed"] is True
    assert second["new_attempts"] == 2
    assert second["skipped_attempts"] == 2
    assert len(second["attempts"]) == 4
    assert call_n["n"] == 4
    # Existing rows preserved
    kept = {a["run_id"] for a in second["attempts"] if a["attempt_index"] < 2}
    assert kept == first_run_ids
    assert second["metrics"]["pass_at_k"]["4"]["value"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_resume_other_tasks_preserved() -> None:
    """Topping up one task must not drop sibling task attempts."""
    plan = plan_suite_run(SUITE, n_attempts=1, max_concurrent_tasks=2)
    plan.task_ids = ["alpha", "beta"]

    async def runner(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        run_id = f"sha256_dead_run_{task_id}"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        result = SimpleNamespace(
            status="PASS",
            score=1.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        return 0, result, {"digest": f"sha256:{task_id}", "run_dir": str(abs_run)}

    first = await execute_suite_run(plan, run_fn=runner)
    suite_id = first["suite_run_id"]

    plan_alpha = plan_suite_run(
        SUITE,
        task_id="alpha",
        n_attempts=2,
        suite_run_id=suite_id,
    )
    call_tasks: list[str] = []

    async def runner2(root, task_id, *, overrides=None, profiles_path=None):  # noqa: ANN001
        call_tasks.append(task_id)
        run_id = f"sha256_dead_run_{task_id}_extra"
        abs_run = Path(root) / ".bora" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        result = SimpleNamespace(
            status="PASS",
            score=1.0,
            evidence_path=str(abs_run),
            logs=str(abs_run),
        )
        return 0, result, {"digest": "sha256:extra", "run_dir": str(abs_run)}

    second = await execute_suite_run(plan_alpha, run_fn=runner2, resume=True)
    task_ids_present = {a["task_id"] for a in second["attempts"]}
    assert "beta" in task_ids_present
    assert "alpha" in task_ids_present
    # only alpha attempt_index=1 is new (index 0 already done)
    assert call_tasks == ["alpha"]
    alpha_attempts = [a for a in second["attempts"] if a["task_id"] == "alpha"]
    assert len(alpha_attempts) == 2
