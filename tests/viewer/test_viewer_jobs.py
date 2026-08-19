"""Harbor-style jobs API tests for local suite-runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ageval.viewer import jobs

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "datasets" / "suite-min"


def _seed_suite_run(db: Path, job_id: str = "suite_demo_job_001") -> str:
    suite_dir = db / ".ageval" / "suite-runs" / job_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "ageval.suite.summary/1",
        "suite_run_id": job_id,
        "dataset_id": "test/suite-min",
        "dataset_version": "0.1.0",
        "agent_label": "codex",
        "model_label": "gpt-test",
        "provider_label": "openai",
        "environment": "local",
        "created_at": "2026-07-14T19:46:20Z",
        "tasks": [
            {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": "run_a"},
            {"task_id": "beta", "status": "FAIL", "score": 0.0, "run_id": "run_b"},
            {"task_id": "gamma", "status": "PASS", "score": 1.0, "run_id": "run_c"},
        ],
        "task_refs": [
            {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": "run_a"},
            {"task_id": "beta", "status": "FAIL", "score": 0.0, "run_id": "run_b"},
            {"task_id": "gamma", "status": "PASS", "score": 1.0, "run_id": "run_c"},
        ],
        "metrics": {
            "pass_rate": 2 / 3,
            "mean_score": 2 / 3,
            "n_tasks": 3,
            "n_pass": 2,
            "n_fail": 1,
            "n_error": 0,
            "missing_score_as": 0.0,
        },
        "exit_code": 1,
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return job_id


def _clean_db(tmp_path: Path) -> Path:
    """Copy fixture without leftover .ageval suite-runs from local smokes."""
    db = tmp_path / "db"
    shutil.copytree(SUITE, db, ignore=shutil.ignore_patterns(".ageval"))
    return db


def test_get_job_from_attempts_only_summary(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = "suite_attempts_only"
    suite_dir = db / ".ageval" / "suite-runs" / job_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema": "ageval.suite.summary/1",
                "suite_run_id": job_id,
                "attempts": [
                    {
                        "task_id": "alpha",
                        "attempt_index": 0,
                        "status": "PASS",
                        "score": 1.0,
                        "run_id": "run_a",
                    },
                    {
                        "task_id": "beta",
                        "attempt_index": 0,
                        "status": "FAIL",
                        "score": 0.0,
                        "run_id": "run_b",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    detail = jobs.get_job(db, job_id)
    assert detail["task_count"] == 2
    ids = {row["task_id"] for row in detail["tasks"]}
    assert ids == {"alpha", "beta"}
    by_id = {row["task_id"]: row for row in detail["tasks"]}
    assert by_id["alpha"]["status"] == "PASS"
    assert by_id["beta"]["status"] == "FAIL"


def test_list_and_get_job(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)

    listed = jobs.list_jobs(db)
    assert listed["count"] == 1
    assert listed["items"][0]["job_id"] == job_id
    assert listed["items"][0]["mean_score"] == pytest.approx(2 / 3)
    assert listed["items"][0]["agent_label"] == "codex"

    detail = jobs.get_job(db, job_id)
    assert detail["task_count"] == 3
    assert detail["tasks"][0]["task_id"] == "alpha"
    assert detail["tasks"][1]["status"] == "FAIL"


def test_job_task_detail_and_command(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    payload = jobs.get_job_task(db, job_id, "beta")
    assert payload["task"]["status"] == "FAIL"
    assert payload["trials"][0]["reward"] == 0.0
    assert "ageval run" in (payload.get("run_command") or "")
    assert "--task beta" in (payload.get("run_command") or "")
    crumbs = payload["breadcrumb"]
    assert crumbs[0]["label"] == "Jobs"
    assert crumbs[0]["href"] == "/"
    assert crumbs[1]["label"] == job_id
    assert crumbs[2]["label"] == "beta"
    assert crumbs[2]["href"] is None


def test_list_empty_without_suite_runs(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    listed = jobs.list_jobs(db)
    assert listed["count"] == 0
    assert listed["items"] == []


def test_list_includes_single_task_attempt(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    run_id = "run_single_alpha"
    evidence = db / ".ageval" / "runs" / run_id
    evidence.mkdir(parents=True)
    (evidence / "result.json").write_text(
        json.dumps(
            {
                "task_id": "alpha",
                "status": "PASS",
                "score": 1.0,
                "created_at": "2026-08-13T12:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    listed = jobs.list_jobs(db)
    assert listed["count"] == 1
    row = listed["items"][0]
    assert row["job_id"] == run_id
    assert row["source_kind"] == "single"
    assert row["source"] == "alpha"
    detail = jobs.get_job(db, run_id)
    assert detail["task_count"] == 1
    assert detail["tasks"][0]["task_id"] == "alpha"


def test_list_includes_task_local_single_attempt(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    run_id = "run_task_local_beta"
    evidence = db / "tasks" / "beta" / ".ageval" / "runs" / run_id
    evidence.mkdir(parents=True)
    (evidence / "result.json").write_text(
        json.dumps(
            {
                "task_id": "beta",
                "status": "FAIL",
                "score": 0.0,
                "created_at": "2026-08-13T13:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    listed = jobs.list_jobs(db)
    row = next(item for item in listed["items"] if item["job_id"] == run_id)
    assert row["source_kind"] == "single"
    assert row["source"] == "beta"
    assert row["task_id"] == "beta"


def test_job_task_exposes_attempt_run_ids_for_k(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = "suite_k2"
    suite_dir = db / ".ageval" / "suite-runs" / job_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "ageval.suite.summary/1",
        "suite_run_id": job_id,
        "dataset_id": "test/suite-min",
        "n_attempts": 2,
        "tasks": [
            {
                "task_id": "alpha",
                "status": "PASS",
                "score": 1.0,
                "run_id": "run_alpha_0",
                "n": 2,
                "c": 1,
            }
        ],
        "attempts": [
            {
                "task_id": "alpha",
                "run_id": "run_alpha_0",
                "status": "PASS",
                "score": 1.0,
                "attempt_index": 0,
            },
            {
                "task_id": "alpha",
                "run_id": "run_alpha_1",
                "status": "FAIL",
                "score": 0.0,
                "attempt_index": 1,
            },
        ],
        "metrics": {"n_tasks": 1, "n_pass": 1, "n_fail": 0, "mean_score": 1.0},
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary) + "\n", encoding="utf-8")

    detail = jobs.get_job(db, job_id)
    row = detail["tasks"][0]
    assert row["attempt_run_ids"] == ["run_alpha_0", "run_alpha_1"]
    assert row["n"] == 2
    assert row.get("previous") == []

    payload = jobs.get_job_task(db, job_id, "alpha")
    assert [t["run_id"] for t in payload["trials"]] == ["run_alpha_0", "run_alpha_1"]
    extra = db / ".ageval" / "runs" / "run_alpha_other"
    extra.mkdir(parents=True)
    (extra / "result.json").write_text(
        json.dumps({"task_id": "alpha", "status": "PASS", "score": 1.0}) + "\n",
        encoding="utf-8",
    )
    listed = jobs.list_jobs(db)
    kinds = {item["job_id"]: item.get("source_kind") for item in listed["items"]}
    assert kinds.get(job_id) == "suite"
    assert kinds.get("run_alpha_other") == "single"
    assert "run_alpha_0" not in kinds
    assert "run_alpha_1" not in kinds


def test_single_task_not_duplicated_when_in_suite(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_suite_run(db)
    evidence = db / ".ageval" / "runs" / "run_a"
    evidence.mkdir(parents=True)
    (evidence / "result.json").write_text(
        json.dumps({"task_id": "alpha", "status": "PASS", "score": 1.0}) + "\n",
        encoding="utf-8",
    )
    listed = jobs.list_jobs(db)
    kinds = {item["job_id"]: item.get("source_kind") for item in listed["items"]}
    assert kinds.get("suite_demo_job_001") == "suite"
    assert "run_a" not in kinds
