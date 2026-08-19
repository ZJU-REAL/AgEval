"""Local Job delete: single erase, suite cascade, fail-closed refusals."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ageval.application.composition import build_local_jobs_commands
from ageval.config.errors import ConfigError
from ageval.viewer import jobs

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def _clean_db(tmp_path: Path) -> Path:
    db = tmp_path / "db"
    shutil.copytree(SUITE, db, ignore=shutil.ignore_patterns(".ageval"))
    return db


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_attempt(
    db: Path, run_id: str, *, task_id: str = "alpha", task_local: bool = False
) -> Path:
    evidence = (
        db / "tasks" / task_id / ".ageval" / "runs" / run_id
        if task_local
        else db / ".ageval" / "runs" / run_id
    )
    _write_json(
        evidence / "result.json",
        {"task_id": task_id, "status": "PASS", "score": 1.0},
    )
    return evidence


def _seed_suite(
    db: Path,
    job_id: str = "suite_demo_job_001",
    *,
    run_ids: list[str] | None = None,
    extra_attempts: list[str] | None = None,
) -> str:
    run_ids = run_ids or ["run_a", "run_b"]
    suite_dir = db / ".ageval" / "suite-runs" / job_id
    tasks = [
        {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": run_ids[0]},
    ]
    refs = [
        {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": run_ids[0]},
    ]
    if len(run_ids) > 1:
        tasks.append({"task_id": "beta", "status": "FAIL", "score": 0.0, "run_id": run_ids[1]})
        refs.append(
            {
                "task_id": "beta",
                "status": "FAIL",
                "score": 0.0,
                "run_id": run_ids[1],
                "attempt_run_ids": extra_attempts or [run_ids[1]],
            }
        )
    _write_json(
        suite_dir / "summary.json",
        {
            "schema": "ageval.suite.summary/1",
            "suite_run_id": job_id,
            "database_id": "test/suite-min",
            "tasks": tasks,
            "task_refs": refs,
            "attempts": [
                {"task_id": "alpha", "run_id": rid}
                if i == 0
                else {"task_id": "beta", "run_id": rid}
                for i, rid in enumerate(run_ids)
            ],
            "metrics": {"n_tasks": len(tasks), "n_pass": 1, "n_fail": max(0, len(tasks) - 1)},
        },
    )
    return job_id


def _job_ids(db: Path) -> set[str]:
    return {item["job_id"] for item in jobs.list_jobs(db)["items"]}


def test_delete_single_removes_attempt_dir(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_attempt(db, "run_single_alpha")
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id="run_single_alpha")
    assert preview["kind"] == "single"
    assert preview["can_delete"] is True
    assert preview["bytes"] > 0
    locators = [p["locator"] for p in preview["paths"]]
    assert ".ageval/runs/run_single_alpha" in locators

    with pytest.raises(ConfigError, match="confirm_required"):
        cmds.delete_job(db, job_id="run_single_alpha")

    out = cmds.delete_job(db, job_id="run_single_alpha", yes=True)
    assert out["ok"] is True
    assert not (db / ".ageval" / "runs" / "run_single_alpha").exists()
    assert "run_single_alpha" not in _job_ids(db)


def test_delete_task_local_single(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    evidence = _seed_attempt(db, "run_task_local", task_id="beta", task_local=True)
    cmds = build_local_jobs_commands()
    cmds.delete_job(db, job_id="run_task_local", yes=True)
    assert not evidence.exists()
    assert "run_task_local" not in _job_ids(db)


def test_delete_suite_cascades_attempts(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite(db, extra_attempts=["run_b", "run_b2"])
    for rid in ("run_a", "run_b", "run_b2"):
        _seed_attempt(db, rid, task_id="alpha" if rid == "run_a" else "beta")
    leftover = _seed_attempt(db, "run_other")

    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id=job_id)
    assert preview["kind"] == "suite"
    assert set(preview["cascade_run_ids"]) >= {"run_a", "run_b", "run_b2"}
    assert any(p["locator"].endswith(f"suite-runs/{job_id}") for p in preview["paths"])

    cmds.delete_job(db, job_id=job_id, yes=True)
    listed = _job_ids(db)
    assert job_id not in listed
    assert "run_a" not in listed
    assert "run_b" not in listed
    assert "run_b2" not in listed
    assert "run_other" in listed
    assert leftover.is_dir()
    assert not (db / ".ageval" / "suite-runs" / job_id).exists()
    assert not (db / ".ageval" / "runs" / "run_a").exists()


def test_delete_suite_cascades_previous_attempts(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = "suite_hist"
    suite_dir = db / ".ageval" / "suite-runs" / job_id
    _write_json(
        suite_dir / "summary.json",
        {
            "schema": "ageval.suite.summary/1",
            "suite_run_id": job_id,
            "database_id": "test/suite-min",
            "tasks": [{"task_id": "alpha", "status": "PASS", "run_id": "run_new"}],
            "task_refs": [
                {
                    "task_id": "alpha",
                    "status": "PASS",
                    "run_id": "run_new",
                    "previous": [{"run_id": "run_old", "status": "ERROR", "attempt_index": 0}],
                }
            ],
            "attempts": [
                {
                    "task_id": "alpha",
                    "run_id": "run_new",
                    "previous": [{"run_id": "run_old", "status": "ERROR", "attempt_index": 0}],
                }
            ],
            "metrics": {"n_tasks": 1, "n_pass": 1},
        },
    )
    _seed_attempt(db, "run_new")
    _seed_attempt(db, "run_old")
    leftover = _seed_attempt(db, "run_other")
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id=job_id)
    assert set(preview["cascade_run_ids"]) >= {"run_new", "run_old"}
    inner = cmds.preview_delete_job(db, job_id="run_old")
    assert inner["can_delete"] is False
    cmds.delete_job(db, job_id=job_id, yes=True)
    assert not (db / ".ageval" / "runs" / "run_old").exists()
    assert leftover.is_dir()


def test_refuse_delete_attempt_without_result(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    live = db / ".ageval" / "runs" / "run_live"
    live.mkdir(parents=True)
    (live / "lock.json").write_text("{}\n", encoding="utf-8")
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id="run_live")
    assert preview["can_delete"] is False
    assert preview["error"]["code"] == "job_in_progress"
    with pytest.raises(ConfigError, match="job_in_progress"):
        cmds.delete_job(db, job_id="run_live", yes=True)
    assert live.is_dir()
    assert "run_live" not in _job_ids(db)


def test_list_jobs_includes_progress_only_suite(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    suite_dir = db / ".ageval" / "suite-runs" / "suite_live"
    _write_json(
        suite_dir / "progress.json",
        {
            "schema": "ageval.suite.progress/1",
            "suite_run_id": "suite_live",
            "status": "running",
            "done": 1,
            "total": 100,
        },
    )
    listed = jobs.list_jobs(db)
    ids = {item["job_id"] for item in listed["items"]}
    assert "suite_live" in ids
    row = next(item for item in listed["items"] if item["job_id"] == "suite_live")
    assert row["status"] == "running"
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id="suite_live")
    assert preview["can_delete"] is True
    assert preview["warning"]["code"] == "job_in_progress"
    detail = jobs.get_job(db, "suite_live")
    assert detail["ok"] is True
    assert detail["job"]["job_id"] == "suite_live"
    assert detail["job"]["status"] == "running"
    assert detail["progress"]["status"] == "running"


def test_refuse_inner_attempt_delete(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_suite(db)
    _seed_attempt(db, "run_a")
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id="run_a")
    assert preview["can_delete"] is False
    assert preview["error"]["code"] == "job_inner_attempt"
    with pytest.raises(ConfigError, match="job_inner_attempt"):
        cmds.delete_job(db, job_id="run_a", yes=True)
    assert (db / ".ageval" / "runs" / "run_a").is_dir()


def test_in_progress_suite_warns_but_deletes(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite(db)
    _seed_attempt(db, "run_a")
    _write_json(
        db / ".ageval" / "suite-runs" / job_id / "progress.json",
        {"schema": "ageval.suite.progress/1", "status": "running", "done": 0, "total": 2},
    )
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id=job_id)
    assert preview["can_delete"] is True
    assert preview["warning"]["code"] == "job_in_progress"
    cmds.delete_job(db, job_id=job_id, yes=True)
    assert not (db / ".ageval" / "suite-runs" / job_id).exists()


def test_live_cancel_request_warns_but_deletes(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite(db)
    (db / ".ageval" / "suite-runs" / job_id / "cancel.requested").write_text(
        "{}\n", encoding="utf-8"
    )
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id=job_id)
    assert preview["can_delete"] is True
    assert preview["warning"]["code"] == "job_in_progress"
    cmds.delete_job(db, job_id=job_id, yes=True)
    assert not (db / ".ageval" / "suite-runs" / job_id).exists()


def test_complete_progress_allows_delete(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite(db)
    _seed_attempt(db, "run_a")
    _seed_attempt(db, "run_b")
    _write_json(
        db / ".ageval" / "suite-runs" / job_id / "progress.json",
        {"schema": "ageval.suite.progress/1", "status": "complete", "done": 2, "total": 2},
    )
    cmds = build_local_jobs_commands()
    cmds.delete_job(db, job_id=job_id, yes=True)
    assert job_id not in _job_ids(db)


def test_refuse_claimed_by_another_suite(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_suite(db, "suite_one", run_ids=["run_shared", "run_only_one"])
    _seed_suite(db, "suite_two", run_ids=["run_shared", "run_only_two"])
    _seed_attempt(db, "run_shared")
    _seed_attempt(db, "run_only_one")
    cmds = build_local_jobs_commands()
    preview = cmds.preview_delete_job(db, job_id="suite_one")
    assert preview["can_delete"] is False
    assert preview["error"]["code"] == "job_claimed_elsewhere"
    with pytest.raises(ConfigError, match="job_claimed_elsewhere"):
        cmds.delete_job(db, job_id="suite_one", yes=True)
    assert (db / ".ageval" / "runs" / "run_shared").is_dir()


def test_refuse_path_escape(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    cmds = build_local_jobs_commands()
    with pytest.raises(ConfigError, match="invalid_package"):
        cmds.preview_delete_job(db, job_id="../etc")
    with pytest.raises(ConfigError, match="invalid_package"):
        cmds.delete_job(db, job_id="a/b", yes=True)


def test_unknown_job(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    cmds = build_local_jobs_commands()
    with pytest.raises(ConfigError, match="unknown_task"):
        cmds.preview_delete_job(db, job_id="missing_job")


def test_confirm_token_mismatch(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_attempt(db, "run_single_alpha")
    cmds = build_local_jobs_commands()
    with pytest.raises(ConfigError, match="confirm_mismatch"):
        cmds.delete_job(db, job_id="run_single_alpha", confirm_token="nope")
    cmds.delete_job(
        db,
        job_id="run_single_alpha",
        confirm_token=cmds.preview_delete_job(db, job_id="run_single_alpha")["confirm_token"],
    )
    assert "run_single_alpha" not in _job_ids(db)
