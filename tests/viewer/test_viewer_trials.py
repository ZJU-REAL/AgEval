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
        json.dumps(
            {
                "task_id": task_id,
                "digest": "sha256:deadbeef",
                "profiles": [
                    {
                        "id": "main",
                        "executor": "acp",
                        "model": "test-model",
                        "options": {"entry": "pi"},
                        "capabilities": {"execution_mode": "acp-stdio"},
                    }
                ],
            },
            indent=2,
        )
        + "\n",
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
                "latency_ms": 1234.5,
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
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "cached_read_tokens": 50,
                "cost": {"amount": 0.001, "currency": "USD"},
                "context": {"used": 200, "size": 100000},
                "sources": {"prompt_usage": True, "usage_update": True},
            },
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
    assert "runtime" in tabs
    assert detail["trial"].get("framework") == "acp"
    assert detail["trial"].get("docker") is None
    actors = detail["trial"].get("actors") or []
    assert len(actors) == 1
    assert actors[0]["role"] == "main"
    assert actors[0]["agent"] == "pi"
    assert actors[0]["model"] == "test-model"
    assert actors[0].get("executor_kind") == "acp"
    assert detail["trial"].get("executor_kind") == "acp"
    assert actors[0]["invokes"] == 1
    assert actors[0]["latency_ms_sum"] == pytest.approx(1234.5)
    assert actors[0]["time_label"]
    assert "1.2s" in actors[0]["time_label"] or "1234ms" in actors[0]["time_label"]
    usage = actors[0].get("usage") or {}
    assert usage.get("input_tokens") == 100
    assert usage.get("output_tokens") == 20
    assert usage.get("cache_hit_rate") == pytest.approx(0.5)
    assert usage.get("cost_amount") == pytest.approx(0.001)
    assert actors[0].get("usage_label")
    assert "in " in actors[0]["usage_label"]
    assert detail["trial"].get("upstream_url") is None


def test_trajectory_steps(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")

    traj = trials.trial_trajectory(db, job_id, "alpha", "run_alpha_1")
    assert traj["step_count"] >= 3
    roles = [s.get("role") for s in traj["steps"] if s.get("role")]
    assert "user" in roles
    assert "assistant" in roles
    assert all(s.get("profile_id") == "main" for s in traj["steps"])


def test_trajectory_tool_call_and_observation_steps(tmp_path: Path) -> None:
    """Viewer fail-open parses tool_call / observation rows for the panel."""
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    root = _write_evidence(db, "run_alpha_1", task_id="alpha")
    inv = root / "agent" / "invocations" / "0001-inv_test"
    traj = [
        {"type": "turn", "role": "user", "content": "read cfg", "turn_index": 1},
        {
            "type": "tool_call",
            "tool_call_id": "call_1",
            "title": "read file",
            "function_name": "read",
            "kind": "read",
            "status": "completed",
            "args": {"path": "/w/a.txt"},
            "turn_index": 1,
            "source": "acp",
        },
        {
            "type": "observation",
            "tool_call_id": "call_1",
            "status": "completed",
            "content": "file body",
            "turn_index": 1,
            "source": "acp",
        },
        {"type": "turn", "role": "assistant", "content": "done", "turn_index": 1},
        {"type": "terminal", "ok": True, "turn_index": 1},
    ]
    (inv / "trajectory.jsonl").write_text(
        "\n".join(json.dumps(x) for x in traj) + "\n", encoding="utf-8"
    )

    payload = trials.trial_trajectory(db, job_id, "alpha", "run_alpha_1")
    types = [s.get("type") for s in payload["steps"]]
    assert "tool_call" in types
    assert "observation" in types
    tool = next(s for s in payload["steps"] if s.get("type") == "tool_call")
    assert tool.get("tool_call_id") == "call_1"
    assert tool.get("kind") == "read"
    assert tool.get("function_name") == "read"
    # args surfaced as content when no content field
    assert tool.get("content") and "a.txt" in tool["content"]
    obs = next(s for s in payload["steps"] if s.get("type") == "observation")
    assert obs.get("content") == "file body"
    assert obs.get("tool_call_id") == "call_1"


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


def test_trial_file_redacts_env_basename(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    evidence = _write_evidence(db, "run_alpha_1", task_id="alpha")
    (evidence / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    payload = trials.trial_file(
        db,
        job_id,
        "alpha",
        "run_alpha_1",
        relpath=".env",
    )
    assert payload["encoding"] == "redacted"
    assert payload["content"] is None
    assert "sk-secret" not in json.dumps(payload)


def test_list_trials_enriches_evidence(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_evidence(db, "run_alpha_1", task_id="alpha")
    # Extra local run for same task (not in suite summary)
    _write_evidence(db, "run_alpha_extra", task_id="alpha")

    listed = trials.list_task_trials(db, job_id, "alpha")
    run_ids = {t["run_id"] for t in listed["trials"]}
    assert run_ids == {"run_alpha_1"}
    assert "run_alpha_extra" not in run_ids
    alpha1 = next(t for t in listed["trials"] if t["run_id"] == "run_alpha_1")
    assert alpha1["has_evidence"] is True
    assert "trajectory" in alpha1["available_tabs"]


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


def _write_multi_role_evidence(db: Path, run_id: str, *, task_id: str = "alpha") -> Path:
    """Two profiles, multiple invs; last usage per profile wins; old used-only shape."""
    root = db / ".bora" / "runs" / run_id
    inv_root = root / "agent" / "invocations"
    inv_root.mkdir(parents=True, exist_ok=True)
    (root / "evaluation").mkdir(parents=True, exist_ok=True)

    (root / "lock.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "digest": "sha256:multi",
                "provenance": {
                    "kind": "reimplementation",
                    "upstream": {
                        "name": "example-upstream",
                        "url": "https://github.com/example/upstream",
                        "ref": "main",
                    },
                },
                "profiles": [
                    {
                        "id": "user-grok",
                        "executor": "acp",
                        "model": "entry-default",
                        "options": {"entry": "grok"},
                        "capabilities": {"execution_mode": "acp-stdio"},
                    },
                    {
                        "id": "service-opencode",
                        "executor": "acp",
                        "model": "glm-5.2",
                        "options": {"entry": "opencode"},
                        "capabilities": {"execution_mode": "acp-stdio"},
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "result.json").write_text(
        json.dumps({"status": "PASS", "score": 1.0, "agent_invocations": 3}) + "\n",
        encoding="utf-8",
    )
    (root / "summary.json").write_text(
        json.dumps({"run_id": run_id, "status": "PASS", "score": 1.0}) + "\n",
        encoding="utf-8",
    )

    invs = [
        ("0001-inv_a", "user-grok", "entry-default", 1000.0, None),
        (
            "0002-inv_b",
            "service-opencode",
            "glm-5.2",
            2000.0,
            # legacy UsageUpdate-only shape — must NOT become tokens
            {"used": 9999, "size": 100000, "cost": {"amount": 0.05, "currency": "USD"}},
        ),
        (
            "0003-inv_c",
            "service-opencode",
            "glm-5.2",
            3000.0,
            {
                "input_tokens": 11433,
                "output_tokens": 140,
                "cached_read_tokens": 8576,
                "cost": {"amount": 0.012, "currency": "USD"},
                "context": {"used": 15925, "size": 1000000},
            },
        ),
    ]
    for dirname, profile_id, model, latency_ms, usage in invs:
        inv = inv_root / dirname
        inv.mkdir(parents=True, exist_ok=True)
        (inv / "metadata.json").write_text(
            json.dumps(
                {
                    "invocation_id": dirname.split("-", 1)[-1],
                    "profile_id": profile_id,
                    "executor_kind": "acp",
                    "model": model,
                    "status": "completed",
                    "latency_ms": latency_ms,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        terminal: dict = {
            "type": "terminal",
            "ok": True,
            "stop_reason": "end_turn",
            "source": "bora",
            "turn_index": 1,
        }
        if usage is not None:
            terminal["usage"] = usage
        lines = [
            {"type": "turn", "role": "user", "content": "hi", "turn_index": 1},
            {"type": "turn", "role": "assistant", "content": "ok", "turn_index": 1},
            terminal,
        ]
        (inv / "trajectory.jsonl").write_text(
            "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
        )
    return root


def test_multi_role_actors_time_usage_and_provenance(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    _write_multi_role_evidence(db, "run_alpha_1", task_id="alpha")

    detail = trials.get_trial(db, job_id, "alpha", "run_alpha_1")
    trial = detail["trial"]
    assert trial.get("upstream_url") == "https://github.com/example/upstream"
    assert trial.get("upstream_name") == "example-upstream"
    actors = trial.get("actors") or []
    assert len(actors) == 2
    by_pid = {a["profile_id"]: a for a in actors}

    user = by_pid["user-grok"]
    assert user["role"] == "user-grok"
    assert user["agent"] == "grok"
    assert user["invokes"] == 1
    assert user["latency_ms_sum"] == pytest.approx(1000.0)
    # No usage on user inv → fail-open
    assert user.get("usage") is None or user.get("usage_label") is None

    service = by_pid["service-opencode"]
    assert service["role"] == "service-opencode"
    assert service["agent"] == "opencode"
    assert service["invokes"] == 2
    assert service["latency_ms_sum"] == pytest.approx(5000.0)
    # Last invoke wins — normalized tokens, not legacy used=9999
    usage = service.get("usage") or {}
    assert usage.get("input_tokens") == 11433
    assert usage.get("output_tokens") == 140
    # inclusion heuristic: cache ≤ input → hit = cache/input
    assert usage.get("cache_relation") == "inclusion"
    assert usage.get("cache_hit_rate") == pytest.approx(8576 / 11433)
    assert usage.get("cost_amount") == pytest.approx(0.012)
    # disjoint heuristic: cache > input → hit = cache/(input+cache)
    disjoint = (
        trials._usage_summary_for_actor(  # noqa: SLF001
            {"input_tokens": 100, "cached_read_tokens": 500}
        )
        or {}
    )
    assert disjoint.get("cache_relation") == "disjoint"
    assert disjoint.get("cache_hit_rate") == pytest.approx(500 / 600)
    assert disjoint.get("display_input_tokens") == 600
    assert "cache 83%" in (disjoint.get("label") or "")
    assert usage.get("context_used") == 15925
    label = service.get("usage_label") or ""
    assert "in " in label and "out " in label
    assert "cache " in label
    assert "$" in label
    # Never surface bare context used as token total
    assert "9999" not in label

    traj = trials.trial_trajectory(db, job_id, "alpha", "run_alpha_1")
    profiles = {s.get("profile_id") for s in traj["steps"]}
    assert "user-grok" in profiles
    assert "service-opencode" in profiles


def test_legacy_usage_cost_only_no_used_as_tokens(tmp_path: Path) -> None:
    """Old evidence with only {used,size,cost}: show cost, never used as tokens."""
    db = _clean_db(tmp_path)
    job_id = _seed_suite_run(db)
    root = db / ".bora" / "runs" / "run_alpha_1"
    inv = root / "agent" / "invocations" / "0001-inv_x"
    inv.mkdir(parents=True, exist_ok=True)
    (root / "lock.json").write_text(
        json.dumps(
            {
                "task_id": "alpha",
                "profiles": [
                    {
                        "id": "main-pi",
                        "executor": "acp",
                        "options": {"entry": "pi"},
                        "capabilities": {"execution_mode": "acp-stdio"},
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "result.json").write_text(json.dumps({"status": "PASS", "score": 1.0}) + "\n")
    (root / "summary.json").write_text(json.dumps({"status": "PASS"}) + "\n")
    (inv / "metadata.json").write_text(
        json.dumps(
            {
                "profile_id": "main-pi",
                "executor_kind": "acp",
                "model": "m",
                "latency_ms": 500,
            }
        )
        + "\n"
    )
    terminal = {
        "type": "terminal",
        "ok": True,
        "usage": {
            "used": 16899,
            "size": 1000000,
            "cost": {"amount": 0.0, "currency": "USD"},
            "sessionUpdate": "usage_update",
        },
    }
    (inv / "trajectory.jsonl").write_text(json.dumps(terminal) + "\n", encoding="utf-8")

    detail = trials.get_trial(db, job_id, "alpha", "run_alpha_1")
    actor = (detail["trial"].get("actors") or [])[0]
    usage = actor.get("usage") or {}
    assert usage.get("input_tokens") is None
    assert usage.get("output_tokens") is None
    assert usage.get("context_used") == 16899
    assert usage.get("cost_amount") == 0.0
    label = actor.get("usage_label") or ""
    # Cost-only label; no token line
    assert "in " not in label
    assert "$" in label or "0" in label
