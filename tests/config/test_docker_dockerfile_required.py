"""Docker L1 packages must declare environment/Dockerfile (or provider.dockerfile)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.helpers.lock import lock_with_profiles

from ageval.config.errors import ERROR_MISSING_REFERENCE, ConfigError


def _write_minimal_docker_pkg(root: Path, *, with_dockerfile: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "run.py").write_text("def run(ctx): ...\n", encoding="utf-8")
    (root / "evaluator.py").write_text("def evaluate(ctx): ...\n", encoding="utf-8")
    (root / "task.yaml").write_text(
        """
format: ageval.task/1
task_id: docker-df-probe


parameters: {}


agent_profiles:
  - id: p1

limits:
  wall_time_seconds: 60
  agent_invocations: 1

artifacts:
  publishable: []

evaluation:
  entrypoint: evaluator:evaluate
  inputs: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    if with_dockerfile:
        env = root / "environment"
        env.mkdir(parents=True, exist_ok=True)
        (env / "Dockerfile").write_text("FROM ageval-attempt:l1\n", encoding="utf-8")


_P1_BINDINGS = {
    "p1": {
        "executor": "acp",
        "model": "entry-default",
        "extensions": [{"plugin": "acp", "options": {"entry": "pi"}}],
    }
}


def test_docker_missing_dockerfile_fails(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write_minimal_docker_pkg(pkg, with_dockerfile=False)
    with pytest.raises(ConfigError) as ei:
        lock_with_profiles(
            pkg,
            "docker-df-probe",
            _P1_BINDINGS,
        )
    assert ei.value.error_code == ERROR_MISSING_REFERENCE
    assert "Dockerfile" in str(ei.value)


def test_docker_with_environment_dockerfile_locks(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write_minimal_docker_pkg(pkg, with_dockerfile=True)
    lock = lock_with_profiles(
        pkg,
        "docker-df-probe",
        _P1_BINDINGS,
    )
    assert lock.task_id == "docker-df-probe"
