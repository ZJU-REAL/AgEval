"""Docker L1 packages must declare environment/Dockerfile (or provider.dockerfile)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError, ERROR_MISSING_REFERENCE
from bora.config.load_and_lock import ConfigCore
from bora.adapters.package_fs import LocalPackageReader


def _write_minimal_docker_pkg(root: Path, *, with_dockerfile: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "harness.py").write_text("def run(ctx): ...\n", encoding="utf-8")
    (root / "evaluator.py").write_text("def evaluate(ctx): ...\n", encoding="utf-8")
    (root / "task.yaml").write_text(
        """
format: bora.task/1
task_id: docker-df-probe

harness:
  runtime: python
  entrypoint: harness:run

parameters: {}

provider:
  kind: docker
  assurance: l1

agent_profiles:
  - id: p1
    executor: acp
    model: entry-default
    options:
      entry: pi

limits:
  wall_time_seconds: 60
  agent_invocations: 1
  environment_actions: 0

artifacts:
  publishable: []

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs: []
  output:
    format: json
""".strip()
        + "\n",
        encoding="utf-8",
    )
    if with_dockerfile:
        env = root / "environment"
        env.mkdir(parents=True, exist_ok=True)
        (env / "Dockerfile").write_text(
            "FROM bora-attempt:l1\n", encoding="utf-8"
        )


def test_docker_missing_dockerfile_fails(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write_minimal_docker_pkg(pkg, with_dockerfile=False)
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "docker-df-probe", capabilities=DeclarationCapabilityCatalog())
    assert ei.value.error_code == ERROR_MISSING_REFERENCE
    assert "Dockerfile" in str(ei.value)



def test_docker_with_environment_dockerfile_locks(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write_minimal_docker_pkg(pkg, with_dockerfile=True)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(
        pkg, "docker-df-probe", capabilities=DeclarationCapabilityCatalog()
    )
    assert lock.task_id == "docker-df-probe"
