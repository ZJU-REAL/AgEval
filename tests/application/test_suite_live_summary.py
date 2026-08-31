"""In-progress summary.json: an observational snapshot over settled tasks (#193).

While the suite runs, ``summary.json`` is rewritten from settled attempts only;
the same file is replaced by the final document on complete / cancel.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from ageval.application.registry_ops.results_command import ResultsCommands
from ageval.application.suite.suite_run import (
    execute_suite_run,
    plan_suite_run,
    request_suite_cancel,
    suite_summary_path,
)
from ageval.config.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "datasets" / "suite-min"


def _copy_fixture(tmp_path: Path) -> Path:
    """Private dataset root: the fixture dir accumulates .ageval state when shared."""
    db = tmp_path / "db"
    db.mkdir()
    for item in SUITE.iterdir():
        if item.name == ".ageval":
            continue
        target = db / item.name
        (shutil.copytree if item.is_dir() else shutil.copyfile)(item, target)
    return db


def _snapshotting_runner(suite_run_id: str, statuses: dict[str, str], *, prefix: str = "live"):
    """Runner that records the on-disk summary.json seen when each unit starts.

    Later units see every earlier unit settled; nothing else.
    """
    seen: dict[str, dict] = {}
    n = {"n": 0}

    async def run(root, task_id, *, overrides=None, profiles_path=None, **kwargs):  # noqa: ANN001
        path = suite_summary_path(Path(root), suite_run_id)
        if path.is_file():
            seen[task_id] = json.loads(path.read_text(encoding="utf-8"))
        n["n"] += 1
        st = statuses[task_id]
        run_id = f"sha256_dead_run_{prefix}_{task_id}_{n['n']}"
        abs_run = Path(root) / ".ageval" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        score = 1.0 if st == "PASS" else (0.0 if st == "FAIL" else None)
        code = 0 if st == "PASS" else (1 if st == "FAIL" else 2)
        result = SimpleNamespace(
            status=st, score=score, evidence_path=str(abs_run), logs=str(abs_run)
        )
        return code, result

    run.seen = seen  # type: ignore[attr-defined]
    return run


@pytest.mark.asyncio
async def test_live_summary_counts_settled_tasks_only(tmp_path: Path) -> None:
    db = _copy_fixture(tmp_path)
    plan = plan_suite_run(db, max_concurrent_tasks=1)
    runner = _snapshotting_runner(
        plan.suite_run_id,
        {"alpha": "PASS", "beta": "ERROR", "delta-fail": "FAIL", "gamma": "PASS"},
    )
    summary = await execute_suite_run(plan, run_fn=runner)

    seen = runner.seen  # type: ignore[attr-defined]
    # alpha started first: nothing settled yet, but the snapshot exists.
    assert seen["alpha"]["status"] == "running"
    assert seen["alpha"]["dataset_id"] == "test/suite-min"
    assert seen["alpha"]["dataset_version"] == "0.1.0"
    assert seen["alpha"]["metrics"]["n_tasks"] == 0
    # beta starts after alpha settled: denominator is settled tasks, not planned.
    assert seen["beta"]["status"] == "running"
    assert seen["beta"]["task_ids"] == ["alpha"]
    assert [t["task_id"] for t in seen["beta"]["tasks"]] == ["alpha"]
    assert seen["beta"]["metrics"]["pass_rate"] == 1.0
    assert seen["beta"]["metrics"]["n_tasks"] == 1
    # delta-fail starts after alpha(PASS) + beta(ERROR): pass rate over 2 settled.
    assert seen["delta-fail"]["metrics"]["pass_rate"] == pytest.approx(1 / 2)
    assert seen["delta-fail"]["metrics"]["n_error"] == 1
    assert "beta" in [t["task_id"] for t in seen["delta-fail"]["tasks"]]
    assert "gamma" not in seen["delta-fail"]["task_ids"]

    # Final document: full planned id set, finished status, locked created_at.
    disk = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))
    assert disk["status"] == "complete"
    assert disk["metrics"]["n_tasks"] == 4
    assert disk["metrics"]["pass_rate"] == pytest.approx(2 / 4)
    assert disk["created_at"] == seen["alpha"]["created_at"]


@pytest.mark.asyncio
async def test_resume_rewrites_snapshot_immediately_and_keeps_created_at(
    tmp_path: Path,
) -> None:
    db = _copy_fixture(tmp_path)
    plan = plan_suite_run(db, task_id="alpha")
    first = await execute_suite_run(
        plan,
        run_fn=_snapshotting_runner(plan.suite_run_id, {"alpha": "PASS"}, prefix="r1"),
    )
    original_created = first["created_at"]

    plan2 = plan_suite_run(db, suite_run_id=first["suite_run_id"])
    runner = _snapshotting_runner(
        plan2.suite_run_id,
        {"alpha": "PASS", "beta": "PASS", "delta-fail": "FAIL", "gamma": "PASS"},
        prefix="r2",
    )
    second = await execute_suite_run(plan2, run_fn=runner, resume=True)

    seen = runner.seen  # type: ignore[attr-defined]
    # First task of the resume sees the snapshot rewritten from settled work
    # only — alpha — with the original created_at and a running status.
    first_seen = next(iter(seen.values()))
    assert first_seen["status"] == "running"
    assert first_seen["task_ids"] == ["alpha"]
    assert first_seen["created_at"] == original_created
    disk = json.loads(Path(second["summary_path"]).read_text(encoding="utf-8"))
    assert disk["status"] == "complete"
    assert disk["metrics"]["n_tasks"] == 4
    assert disk["created_at"] == original_created
    assert disk["resumed"] is True


@pytest.mark.asyncio
async def test_cancelled_suite_writes_cancelled_status(tmp_path: Path) -> None:
    db = _copy_fixture(tmp_path)
    plan = plan_suite_run(db)
    request_suite_cancel(db, plan.suite_run_id)
    runner = _snapshotting_runner(plan.suite_run_id, {"alpha": "PASS"}, prefix="cx")
    summary = await execute_suite_run(plan, run_fn=runner)

    disk = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))
    assert disk["status"] == "cancelled"
    assert runner.seen == {}  # type: ignore[attr-defined]  # no unit ever started


def _never_client(*args: object, **kwargs: object) -> object:
    raise AssertionError("registry client must not be reached for this summary")


def _seed_upload_db(tmp_path: Path, *, status: str | None) -> Path:
    db = tmp_path / "db"
    db.mkdir()
    (db / "ageval.yaml").write_text(
        "format: ageval.dataset/1\nid: test/db\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    suite_dir = db / ".ageval" / "suite-runs" / "suite_up_001"
    suite_dir.mkdir(parents=True)
    summary: dict[str, object] = {
        "schema": "ageval.suite.summary/1",
        "suite_run_id": "suite_up_001",
        "dataset_id": "test/db",
        "dataset_version": "0.1.0",
        "attempts": [
            {"task_id": "a", "attempt_index": 0, "status": "PASS", "run_id": "a0"}
        ],
        "tasks": [{"task_id": "a", "status": "PASS", "score": 1.0, "run_id": "a0"}],
        "metrics": {
            "pass_rate": 1.0,
            "mean_score": 1.0,
            "n_tasks": 1,
            "n_pass": 1,
            "n_fail": 0,
            "n_error": 0,
            "missing_score_as": 0.0,
        },
        "exit_code": 0,
    }
    if status is not None:
        summary["status"] = status
    (suite_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return db


@pytest.mark.parametrize("status", ["running", "cancelling"])
def test_upload_suite_refuses_live_snapshot(tmp_path: Path, status: str) -> None:
    db = _seed_upload_db(tmp_path, status=status)
    cmds = ResultsCommands(client_factory=_never_client)
    with pytest.raises(ConfigError) as excinfo:
        cmds.upload_suite_result(db, suite_run_id="suite_up_001")
    assert excinfo.value.error_code == "suite_in_progress"


def test_upload_suite_complete_summary_passes_status_gate(tmp_path: Path) -> None:
    db = _seed_upload_db(tmp_path, status="complete")
    cmds = ResultsCommands(client_factory=_never_client)
    # The status gate passes; the upload then reaches the (refusing) client.
    with pytest.raises(AssertionError, match="registry client"):
        cmds.upload_suite_result(db, suite_run_id="suite_up_001")
