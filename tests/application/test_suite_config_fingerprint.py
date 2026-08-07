"""Suite config fingerprint / homogeneity (#42)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bora.application.suite_config_fingerprint import (
    actors_summary_from_profiles,
    compute_suite_config_fields,
    fingerprint_for_actors,
)
from bora.application.suite_run import execute_suite_run, plan_suite_run

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def test_actors_summary_sorted_and_secret_free() -> None:
    profiles = [
        {
            "id": "worker",
            "executor": "acp",
            "model": "m2",
            "api_key": "SECRET_LOCATOR",
            "options": {"entry": "pi"},
        },
        {
            "id": "planner",
            "executor": "acp",
            "model": "m1",
            "options": {"entry": "codex"},
        },
    ]
    actors = actors_summary_from_profiles(profiles)
    assert [a["profile_id"] for a in actors] == ["planner", "worker"]
    assert actors[0]["entry"] == "codex"
    assert actors[1]["entry"] == "pi"
    blob = str(actors)
    assert "SECRET" not in blob
    assert "api_key" not in blob


def test_homogeneous_true_identical_topology() -> None:
    a = actors_summary_from_profiles(
        [{"id": "solo", "executor": "acp", "model": "x", "options": {"entry": "pi"}}]
    )
    fields = compute_suite_config_fields([a, a, a])
    assert fields["config_homogeneous"] is True
    assert fields["config_fingerprint"].startswith("sha256:")
    assert fields["actors_summary"] == a
    assert fields["agent_label"] == "pi"
    assert fields["model_label"] == "x"


def test_heterogeneous_false_different_topology() -> None:
    single = actors_summary_from_profiles(
        [{"id": "solo", "executor": "acp", "model": "x", "options": {"entry": "pi"}}]
    )
    multi = actors_summary_from_profiles(
        [
            {"id": "a", "executor": "acp", "model": "m1", "options": {"entry": "codex"}},
            {"id": "b", "executor": "acp", "model": "m2", "options": {"entry": "pi"}},
        ]
    )
    fields = compute_suite_config_fields([single, multi])
    assert fields["config_homogeneous"] is False
    # Labels suppressed when not comparable as one combo
    assert fields["agent_label"] == ""
    assert fields["model_label"] == ""


def test_heterogeneous_false_same_roles_different_models() -> None:
    a = actors_summary_from_profiles(
        [{"id": "solo", "executor": "acp", "model": "gpt-a", "options": {"entry": "codex"}}]
    )
    b = actors_summary_from_profiles(
        [{"id": "solo", "executor": "acp", "model": "gpt-b", "options": {"entry": "codex"}}]
    )
    fields = compute_suite_config_fields([a, b])
    assert fields["config_homogeneous"] is False


def test_fingerprint_stable() -> None:
    actors = actors_summary_from_profiles(
        [
            {"id": "b", "executor": "openai-http", "model": "m"},
            {"id": "a", "executor": "acp", "model": "n", "options": {"entry": "pi"}},
        ]
    )
    assert fingerprint_for_actors(actors) == fingerprint_for_actors(list(reversed(actors)))


@pytest.mark.asyncio
async def test_suite_summary_includes_homogeneous_config() -> None:
    plan = plan_suite_run(SUITE, max_concurrent_tasks=2)
    plan.task_ids = ["alpha", "beta"]

    async def stub(root, task_id, *, overrides=None):  # noqa: ANN001
        result = SimpleNamespace(status="PASS", score=1.0, evidence_path=None, logs=None)
        return 0, result, {"digest": f"sha256:{task_id}"}

    summary = await execute_suite_run(plan, run_fn=stub)
    assert "config_fingerprint" in summary
    assert summary["config_fingerprint"].startswith("sha256:")
    assert summary["config_homogeneous"] is True
    assert isinstance(summary["actors_summary"], list)
    # suite-min has empty agent_profiles → empty actors
    assert summary["actors_summary"] == []
    assert "no suite-level" in summary["note"]
