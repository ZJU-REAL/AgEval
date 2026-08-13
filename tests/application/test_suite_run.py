"""Spec 22 suite scheduler unit/integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from bora.application.suite.suite_run import (
    execute_suite_run,
    extract_run_id,
    get_inflight_peak,
    plan_suite_run,
    reset_inflight_metrics,
)
from bora.config.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def test_extract_run_id_from_absolute_or_relative(tmp_path: Path) -> None:
    root = tmp_path / "db"
    run_id = "sha256_abc_run_deadbeef"
    abs_run = root / ".bora" / "runs" / run_id
    abs_run.mkdir(parents=True)
    assert extract_run_id(root, abs_run) == run_id
    assert extract_run_id(root, str(abs_run)) == run_id
    assert extract_run_id(root, f".bora/runs/{run_id}") == run_id
    assert extract_run_id(root, run_id) == run_id


def test_plan_full_and_single() -> None:
    plan = plan_suite_run(SUITE)
    assert plan.database_id == "test/suite-min"
    assert set(plan.task_ids) >= {"alpha", "beta", "gamma", "delta-fail"}
    assert plan.max_concurrent_tasks == 2  # from defaults

    one = plan_suite_run(SUITE, task_id="alpha", max_concurrent_tasks=4)
    assert one.task_ids == ["alpha"]
    assert one.max_concurrent_tasks == 1  # single-task forces 1


def test_plan_rejects_bad_n() -> None:
    with pytest.raises(ConfigError):
        plan_suite_run(SUITE, max_concurrent_tasks=0)


@pytest.mark.asyncio
async def test_concurrency_cap_with_stub_runner() -> None:
    plan = plan_suite_run(SUITE, max_concurrent_tasks=2)
    # Only the three fast pass-ish ids for timing
    plan.task_ids = ["alpha", "beta", "gamma"]
    reset_inflight_metrics()

    async def slow_run(root, task_id, *, overrides=None, profiles_path=None, **kwargs):  # noqa: ANN001
        await asyncio.sleep(0.15)
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

    summary = await execute_suite_run(plan, run_fn=slow_run)
    assert summary["exit_code"] == 0
    assert summary["counts"]["pass"] == 3
    assert get_inflight_peak() <= 2
    assert summary["inflight_peak"] <= 2
    note = summary.get("note", "")
    assert "no suite-level" in note
    path = Path(summary["summary_path"])
    assert path.is_file()
    # System suite_run_id is bare 8-hex (no suite_ prefix).
    assert len(path.parent.name) == 8
    assert all(c in "0123456789abcdef" for c in path.parent.name)
    for row in summary["tasks"]:
        assert "result_ref" not in row
        assert "evidence_ref" not in row
        assert row["run_id"] and row["run_id"].startswith("sha256_dead_run_")


@pytest.mark.asyncio
async def test_fail_continues_others() -> None:
    plan = plan_suite_run(SUITE, max_concurrent_tasks=2)
    plan.task_ids = ["alpha", "beta", "delta-fail"]

    async def mixed(root, task_id, *, overrides=None, profiles_path=None, **kwargs):  # noqa: ANN001
        await asyncio.sleep(0.05)
        if task_id == "delta-fail":
            result = SimpleNamespace(status="FAIL", score=0.0, evidence_path="x", logs="x")
            return 1, result, {"digest": "sha256:fail", "run_dir": "x"}
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path="y", logs="y")
        return 0, result, {"digest": "sha256:ok", "run_dir": "y"}

    summary = await execute_suite_run(plan, run_fn=mixed)
    assert summary["exit_code"] == 1
    assert summary["counts"]["pass"] == 2
    assert summary["counts"]["fail"] == 1
    assert len(summary["tasks"]) == 3


@pytest.mark.asyncio
async def test_error_exit_code() -> None:
    plan = plan_suite_run(SUITE, max_concurrent_tasks=1)
    plan.task_ids = ["alpha", "beta"]

    async def one_error(root, task_id, *, overrides=None, profiles_path=None, **kwargs):  # noqa: ANN001
        if task_id == "beta":
            result = SimpleNamespace(status="ERROR", score=None, evidence_path=None, logs=None)
            return 2, result, {"digest": None}
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path="y", logs="y")
        return 0, result, {"digest": "sha256:ok"}

    summary = await execute_suite_run(plan, run_fn=one_error)
    assert summary["exit_code"] == 2
    assert summary["counts"]["error"] == 1
