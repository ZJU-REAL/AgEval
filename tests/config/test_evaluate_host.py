"""Lock: evaluate_host.isolated, tree publishables, and egress fail closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.helpers.lock import job_document, lock_standalone

from ageval.config.errors import ConfigError
from ageval.config.model import thaw
from ageval.config.profiles import parse_job_mapping

SOLVER = {
    "executor": "acp",
    "model": "entry-default",
    "options": {"entry": "codex"},
    "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
}
DOCKER_SOLVER = {
    "executor": "acp",
    "model": "entry-default",
    "options": {"entry": "codex"},
    "extensions": [{"plugin": "acp"}, {"plugin": "docker"}],
}
TASK_YAML = """format: ageval.task/1
task_id: isolated
agent_profiles:
  - id: solver
artifacts:
  publishable:
    - id: result
      path: artifacts/result.json
evaluation:
  inputs:
    - artifact: result
      target: artifacts/result.json
"""
TREE_YAML = """format: ageval.task/1
task_id: isolated
agent_profiles:
  - id: solver
artifacts:
  publishable:
    - id: repo
      path: workspace
      kind: tree
      exclude: [target, "*.so", .git]
evaluation:
  inputs:
    - artifact: repo
      target: workspace
"""


def _standalone(root: Path, *, task_yaml: str = TASK_YAML, files: tuple[str, ...] = ()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "task.yaml").write_text(task_yaml, encoding="utf-8")
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#\n", encoding="utf-8")
    return root


def _lock(root: Path, **kwargs: Any) -> Any:
    return lock_standalone(root, "isolated", **kwargs)


def test_omit_evaluate_host_is_same_box_lock(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        files=("run.py", "evaluator.py", "environment/evaluate.Dockerfile"),
    )
    locked = _lock(root, job=job_document({"solver": dict(SOLVER)}))
    refs = thaw(locked.resolved_references)
    assert "environment_evaluate_dockerfile" not in refs
    overlay = thaw(locked.job_overlay)
    assert "evaluate_host" not in overlay


def test_isolated_docker_with_evaluate_dockerfile_locks(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        files=("run.py", "evaluator.py", "environment/evaluate.Dockerfile"),
    )
    locked = _lock(
        root,
        job=job_document(
            {"solver": dict(DOCKER_SOLVER)},
            environment="docker",
            evaluate_host={"isolated": True},
        ),
    )
    refs = thaw(locked.resolved_references)
    assert refs["environment_evaluate_dockerfile"] == "environment/evaluate.Dockerfile"
    overlay = thaw(locked.job_overlay)
    assert overlay["evaluate_host"] == {"isolated": True}
    assert overlay["environment"] == "docker"


def test_isolated_docker_with_evaluation_image_locks(tmp_path: Path) -> None:
    yaml = TASK_YAML + "  docker_image: ageval-eval:grader\n"
    root = _standalone(tmp_path / "pkg", task_yaml=yaml, files=("run.py", "evaluator.py"))
    locked = _lock(
        root,
        job=job_document(
            {"solver": dict(DOCKER_SOLVER)},
            environment="docker",
            evaluate_host={"isolated": True},
        ),
    )
    refs = thaw(locked.resolved_references)
    assert refs["evaluation_docker_image"] == "ageval-eval:grader"


def test_isolated_without_recipe_fails_closed(tmp_path: Path) -> None:
    root = _standalone(tmp_path / "pkg", files=("run.py", "evaluator.py"))
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(DOCKER_SOLVER)},
                environment="docker",
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "evaluate.Dockerfile" in caught.value.message


def test_isolated_local_fails_closed(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        files=("run.py", "evaluator.py", "environment/evaluate.Dockerfile"),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(SOLVER)},
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "docker" in caught.value.message


def test_unknown_evaluate_host_key_fails_closed() -> None:
    with pytest.raises(ConfigError) as caught:
        parse_job_mapping(
            {
                "format": "ageval.profiles/1",
                "environment": "docker",
                "evaluate_host": {"isolated": True, "sidecar": True},
                "agent_profiles": {"solver": dict(DOCKER_SOLVER)},
            }
        )
    assert caught.value.error_code == "invalid_schema"
    assert "unknown evaluate_host keys" in caught.value.message


def test_tree_publishable_round_trips_into_refs(tmp_path: Path) -> None:
    root = _standalone(tmp_path / "pkg", task_yaml=TREE_YAML, files=("run.py", "evaluator.py"))
    locked = _lock(root, job=job_document({"solver": dict(SOLVER)}))
    (row,) = thaw(locked.resolved_references)["artifacts"]
    assert row["id"] == "repo"
    assert row["kind"] == "tree"
    assert row["exclude"] == ["target", "*.so", ".git"]
    assert thaw(locked.evaluation)["inputs"][0]["target"] == "workspace"


def test_unknown_publishable_key_fails_closed(tmp_path: Path) -> None:
    yaml = TASK_YAML.replace(
        "path: artifacts/result.json",
        "path: artifacts/result.json\n      scrape: chat",
    )
    root = _standalone(tmp_path / "pkg", task_yaml=yaml, files=("run.py", "evaluator.py"))
    with pytest.raises(ConfigError) as caught:
        _lock(root, job=job_document({"solver": dict(SOLVER)}))
    assert caught.value.error_code == "invalid_schema"
    assert "unknown artifacts.publishable keys" in caught.value.message


def test_exclude_without_tree_fails_closed(tmp_path: Path) -> None:
    yaml = TASK_YAML.replace(
        "path: artifacts/result.json",
        "path: artifacts/result.json\n      exclude: [target]",
    )
    root = _standalone(tmp_path / "pkg", task_yaml=yaml, files=("run.py", "evaluator.py"))
    with pytest.raises(ConfigError) as caught:
        _lock(root, job=job_document({"solver": dict(SOLVER)}))
    assert caught.value.error_code == "invalid_schema"
    assert "kind: tree" in caught.value.message


def test_egress_llm_on_docker_locks(tmp_path: Path) -> None:
    root = _standalone(tmp_path / "pkg", files=("run.py", "evaluator.py"))
    locked = _lock(
        root,
        job=job_document(
            {"solver": dict(DOCKER_SOLVER)},
            environment="docker",
            environment_options={"egress": "llm"},
        ),
    )
    overlay = thaw(locked.job_overlay)
    assert overlay["environment_options"]["egress"] == "llm"


def test_egress_llm_on_local_fails_closed(tmp_path: Path) -> None:
    root = _standalone(tmp_path / "pkg", files=("run.py", "evaluator.py"))
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(SOLVER)},
                environment_options={"egress": "llm"},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "egress" in caught.value.message


NAMED_YAML = """format: ageval.task/1
task_id: isolated
agent_profiles:
  - id: solver
artifacts:
  publishable:
    - id: repo
      path: workspace
      kind: tree
      exclude: [target]
evaluation:
  inputs:
    - artifact: repo
      target: workspace
  environments:
    audit:
      dockerfile: environment/evaluate/audit/Dockerfile
    verification:
      dockerfile: environment/evaluate/verification/Dockerfile
"""


def test_named_environments_lock_and_ignore_singular_recipe(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=NAMED_YAML,
        files=(
            "run.py",
            "evaluator.py",
            "environment/evaluate.Dockerfile",
            "environment/evaluate/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    locked = _lock(
        root,
        job=job_document(
            {"solver": dict(DOCKER_SOLVER)},
            environment="docker",
            evaluate_host={"isolated": True},
        ),
    )
    refs = thaw(locked.resolved_references)
    assert "environment_evaluate_dockerfile" not in refs
    assert "evaluation_docker_image" not in refs
    assert refs["evaluation_environments"] == {
        "audit": {"dockerfile": "environment/evaluate/audit/Dockerfile"},
        "verification": {"dockerfile": "environment/evaluate/verification/Dockerfile"},
    }


def test_named_environments_without_isolated_fails_closed(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=NAMED_YAML,
        files=(
            "run.py",
            "evaluator.py",
            "environment/evaluate/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document({"solver": dict(DOCKER_SOLVER)}, environment="docker"),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "evaluate_host.isolated" in caught.value.message


def test_named_environments_on_local_fails_closed(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=NAMED_YAML,
        files=(
            "run.py",
            "evaluator.py",
            "environment/evaluate/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(SOLVER)},
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "docker" in caught.value.message


def test_named_environment_missing_dockerfile_fails_closed(tmp_path: Path) -> None:
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=NAMED_YAML,
        files=("run.py", "evaluator.py", "environment/evaluate/audit/Dockerfile"),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(DOCKER_SOLVER)},
                environment="docker",
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "missing_reference"
    assert "verification" in caught.value.message


def test_named_environment_unknown_key_fails_closed(tmp_path: Path) -> None:
    yaml = NAMED_YAML.replace(
        "dockerfile: environment/evaluate/audit/Dockerfile",
        "dockerfile: environment/evaluate/audit/Dockerfile\n      sidecar: true",
    )
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=yaml,
        files=(
            "run.py",
            "evaluator.py",
            "environment/evaluate/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(DOCKER_SOLVER)},
                environment="docker",
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "unknown evaluation environment keys" in caught.value.message


def test_named_environment_invalid_name_fails_closed(tmp_path: Path) -> None:
    yaml = NAMED_YAML.replace("    audit:", "    Audit:")
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=yaml,
        files=(
            "run.py",
            "evaluator.py",
            "environment/evaluate/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(DOCKER_SOLVER)},
                environment="docker",
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "environment name" in caught.value.message


def test_named_environment_dockerfile_under_gold_fails_closed(tmp_path: Path) -> None:
    yaml = NAMED_YAML.replace(
        "dockerfile: environment/evaluate/audit/Dockerfile",
        "dockerfile: evaluation/audit/Dockerfile",
    )
    root = _standalone(
        tmp_path / "pkg",
        task_yaml=yaml,
        files=(
            "run.py",
            "evaluator.py",
            "evaluation/audit/Dockerfile",
            "environment/evaluate/verification/Dockerfile",
        ),
    )
    with pytest.raises(ConfigError) as caught:
        _lock(
            root,
            job=job_document(
                {"solver": dict(DOCKER_SOLVER)},
                environment="docker",
                evaluate_host={"isolated": True},
            ),
        )
    assert caught.value.error_code == "invalid_schema"
    assert "evaluation/" in caught.value.message


def test_unknown_egress_value_fails_closed() -> None:
    with pytest.raises(ConfigError) as caught:
        parse_job_mapping(
            {
                "format": "ageval.profiles/1",
                "environment": "docker",
                "environment_options": {"egress": "none"},
                "agent_profiles": {"solver": dict(DOCKER_SOLVER)},
            }
        )
    assert caught.value.error_code == "invalid_schema"
    assert "egress" in caught.value.message
