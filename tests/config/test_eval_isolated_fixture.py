"""In-repo isolated evaluate fixture locks; omit the switch ignores the recipe."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.lock import lock_task

from ageval.config.model import thaw
from ageval.config.profiles import load_job_document

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "datasets" / "eval-isolated-min"


def test_isolated_fixture_locks_with_evaluate_dockerfile() -> None:
    locked = lock_task(
        FIXTURE,
        "publish-tree",
        job=load_job_document(FIXTURE / "profiles.yaml"),
    )
    refs = thaw(locked.resolved_references)
    assert refs["environment_evaluate_dockerfile"] == "environment/evaluate.Dockerfile"
    overlay = thaw(locked.job_overlay)
    assert overlay["evaluate_host"] == {"isolated": True}
    artifacts = refs["artifacts"]
    assert artifacts[0]["kind"] == "tree"
    assert artifacts[0]["exclude"] == ["target", "*.so", ".git"]
    assert "evaluation_dir" not in refs


def test_same_box_profile_ignores_evaluate_dockerfile() -> None:
    locked = lock_task(
        FIXTURE,
        "publish-tree",
        job=load_job_document(FIXTURE / "profiles.same-box.yaml"),
    )
    refs = thaw(locked.resolved_references)
    assert "environment_evaluate_dockerfile" not in refs
    overlay = thaw(locked.job_overlay)
    assert "evaluate_host" not in overlay
