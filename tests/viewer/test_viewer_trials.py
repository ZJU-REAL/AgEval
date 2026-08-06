"""Attempt / trial evidence API tests for local viewer (#26)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bora.config.errors import ConfigError
from bora.viewer import jobs, trials

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def _seed_suite_run(db: Path, job_id: str = "suite_demo_job_001") -> str:
    suite_dir = db / ".bora" / "suite-runs" / job_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "bora.suite.summary/1",
        "suite_run_id": job_id,
        "database_id": "test/suite-min",
        "database_version": "0.1.0",
        "agent_label": "codex",
        "model_label": "gpt-test",
        "provider_label": "openai",
        "environment": "local",
        "created_at": "2026-07-14T19:46:20Z",
        "tasks": [
            {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": "run_alpha_1"},
            {"task_id": "beta", "status": "FAIL", "score": 0.0, "run_id": "run_beta_1"},
        ],
        "task_refs": [
            {"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": "run_alpha_1"},
            {"task_id": "beta", "status": "FAIL", "score": 0.0, "run_id": "run_beta_1"},
        ],
        "metrics": {
            "pass_rate": 0.5,
            "mean_score": 0.5,
            "n_tasks": 2,
            "n_pass": 1,
            "n_fail": 1,
            "n_error": 0,
            "missing_score_as": 0.0,
        },
        "exit_code": 1,
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return job_id


def _write_evidence(db: Path, run_id: str, *, task_id: str = "alpha") -> Path:
    root = db / ".bora" / "runs" / run_id
    inv = root / "agent" / "invocations" / "0001-inv_test"
    inv.mkdir(parents=True, exist_ok=True)
    (root / "evaluation").mkdir(parents=True, exist_ok=True)
    (root / "harness").mkdir(parents=True, exist_ok=True)

    (root / "lock.json").write_text(
        json.dumps({"task_id": task_id, "digest": "sha256:deadbeef"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "result.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "score": 1.0,
                "error": None,
                "agent_invocations": 1,
                "harness_kind": "completed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "summary.json").write_text(
        json.dumps(
            {
                "schema": "bora.evidence.summary/1",
                "run_id": run_id,
                "status": "PASS",
                "score": 1.0,
                "agent_invocations": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "effects.jsonl").write_text(
        json.dumps({"kind": "effect", "ok": True}) + "\n", encoding="utf-8"
    )
    (root / "cleanup.json").write_text(json.dumps({"ok": True}) + "\n", encoding="utf-8")
    (root / "evaluation" / "raw.json").write_text(
        json.dumps({"verdict": "PASS", "score": 1.0}) + "\n", encoding="utf-8"
    )
    (inv / "metadata.json").write_text(
        json.dumps(
            {
                "invocation_id": "inv_test",
                "profile_id": "main",
                "executor_kind": "acp",
                "model": "test-model",
                "status": "completed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    traj = [
        {"type": "turn", "role": "user", "content": "hello", "turn_index": 1, "source": "bora"},
        {
            "type": "turn",
            "role": "assistant",
            "content": "world",
            "turn_index": 1,
            "source": "acp",
        },
        {
            "type": "terminal",
            "ok": True,
            "stop_reason": "end_turn",
            "source": "bora",
            "turn_index": 1,
        },
    ]
    (inv / "trajectory.jsonl").write_text(
        "\n".join(json.dumps(x) for x in traj) + "\n", encoding="utf-8"
    )
    (inv / "final-response.json").write_text(
        json.dumps({"content": "world"}) + "\n", encoding="utf-8"
    )
    return root


def _clean_db(tmp_path: Path) -> Path:
    db = tmp_path / "db"
    shutil.copytree(SUITE, db, ignore=shutil.ignore_patterns(".bora"))
    return db


def test_resolve_and_trial_detail(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")

    evidence = trials.resolve_evidence_root(db, "run_alpha_1", task_id="alpha")
    assert evidence.is_dir()
    assert (evidence / "lock.json").is_file()

    detail = trials.get_trial(db, job_id, "alpha", "run_alpha_1")
    assert detail["ok"] is True
    assert detail["trial"]["run_id"] == "run_alpha_1"
    assert detail["trial"]["status"] == "PASS"
    tabs = detail["trial"]["available_tabs"]
    assert "trajectory" in tabs
    assert "agent" in tabs
    assert "verifier" in tabs
    assert "lock" in tabs
    assert "log" in tabs
    assert "PASS" not in (detail["trial"].get("note") or "") or "not PASS" in (
        detail["trial"].get("note") or ""
    )


def test_trajectory_steps(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")

    traj = trials.trial_trajectory(db, job_id, "alpha", "run_alpha_1")
    assert traj["step_count"] >= 3
    roles = [s.get("role") for s in traj["steps"] if s.get("role")]
    assert "user" in roles
    assert "assistant" in roles
    assert "not PASS" in (traj.get("note") or "")


def test_tree_and_file_and_traversal(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")

    tree = trials.trial_tree(db, job_id, "alpha", "run_alpha_1", scope="agent")
    paths = {e["path"] for e in tree["entries"]}
    assert any("trajectory.jsonl" in p for p in paths)

    file_payload = trials.trial_file(
        db,
        job_id,
        "alpha",
        "run_alpha_1",
        relpath="lock.json",
    )
    assert file_payload["encoding"] == "utf-8"
    assert "task_id" in (file_payload.get("content") or "")

    with pytest.raises(ConfigError):
        trials.trial_file(
            db,
            job_id,
            "alpha",
            "run_alpha_1",
            relpath="../escape.txt",
        )


def test_list_trials_enriches_evidence(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")
    # Extra local run for same task (not in suite summary)
    _write_evidence(db, "run_alpha_extra", task_id="alpha")

    listed = trials.list_task_trials(db, job_id, "alpha")
    run_ids = {t["run_id"] for t in listed["trials"]}
    assert "run_alpha_1" in run_ids
    assert "run_alpha_extra" in run_ids
    alpha1 = next(t for t in listed["trials"] if t["run_id"] == "run_alpha_1")
    assert alpha1["has_evidence"] is True
    assert "trajectory" in alpha1["available_tabs"]


def test_task_page_uses_enriched_trials(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_beta_1", task_id="beta")
    # Server path logic: merge list into get_job_task shape
    base = jobs.get_job_task(db, job_id, "beta")
    listed = trials.list_task_trials(db, job_id, "beta")
    base["trials"] = listed["trials"]
    assert len(base["trials"]) >= 1
    assert base["trials"][0]["run_id"] == "run_beta_1"
    assert base["trials"][0].get("has_evidence") is True


def test_missing_run_raises(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    _seed_suite_run(db)
    with pytest.raises(ConfigError):
        trials.resolve_evidence_root(db, "does_not_exist")


def test_path_ids_reject_traversal(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    with pytest.raises(ConfigError):
        jobs.get_job(db, "../etc")
    with pytest.raises(ConfigError):
        jobs.get_job_task(db, job_id, "../alpha")
    with pytest.raises(ConfigError):
        trials.resolve_evidence_root(db, "run_alpha_1/../x", task_id="alpha")
    with pytest.raises(ConfigError):
        trials.trial_file(
            db,
            job_id,
            "alpha",
            "run_alpha_1",
            relpath="/etc/passwd",
        )


def test_cross_task_evidence_rejected(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    # Evidence locked to alpha, requested under beta
    _write_evidence(db, "run_alpha_1", task_id="alpha")
    with pytest.raises(ConfigError):
        trials.resolve_evidence_root(db, "run_alpha_1", task_id="beta", require_task_match=True)
    with pytest.raises(ConfigError):
        trials.trial_trajectory(db, job_id, "beta", "run_alpha_1")


def test_missing_evidence_suite_row_ok(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    # suite has run_beta_1 but no on-disk evidence
    detail = trials.get_trial(db, job_id, "beta", "run_beta_1")
    assert detail["trial"]["has_evidence"] is False
    assert detail["trial"]["available_tabs"] == []
    assert detail["trial"]["status"] == "FAIL"
