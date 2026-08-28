"""In-repo named evaluate fixture locks; unused recipe is recorded, not started."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.lock import lock_task

from ageval.config.model import thaw
from ageval.config.profiles import load_job_document

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "datasets" / "eval-named-min"


def test_named_fixture_locks_and_ignores_singular_recipe() -> None:
    locked = lock_task(
        FIXTURE,
        "publish-tree",
        job=load_job_document(FIXTURE / "profiles.yaml"),
    )
    refs = thaw(locked.resolved_references)
    assert "environment_evaluate_dockerfile" not in refs
    assert refs["evaluation_environments"] == {
        "audit": {"dockerfile": "environment/evaluate/audit/Dockerfile"},
        "unused": {"dockerfile": "environment/evaluate/unused/Dockerfile"},
    }
    overlay = thaw(locked.job_overlay)
    assert overlay["evaluate_host"] == {"isolated": True}
    assert overlay["environment"] == "docker"
