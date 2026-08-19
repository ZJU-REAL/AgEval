"""Config lock validation for provider.agent_isolation (Spec 18 Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.adapters.package_fs import LocalPackageReader
from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.errors import ConfigError
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import thaw
from ageval.provider.isolation import parse_logical_topology
from ageval.provider.targets import IsolationMode


def _write_pkg(root: Path, yaml_body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "task.yaml").write_text(yaml_body, encoding="utf-8")
    (root / "harness.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (root / "evaluator.py").write_text("def evaluate(i): return {}\n", encoding="utf-8")
    env = root / "environment"
    env.mkdir(exist_ok=True)
    (env / "Dockerfile").write_text("FROM ageval-attempt:l1\n", encoding="utf-8")
    return root


_BASE = """
format: ageval.task/1
task_id: iso-test
harness:
  runtime: python
  entrypoint: harness:run
parameters: {}
provider:
  kind: docker
  assurance: l1
  platform: linux/arm64
  network: bridge
  agent_isolation:
    mode: shared-container
    groups:
      - id: g1
        actors:
          - id: a1
            profiles: [p1]
        shared_write: [workspace/team]
agent_profiles:
  - id: p1
limits:
  wall_time_seconds: 60
  agent_invocations: 2
  environment_actions: 0
artifacts:
  publishable:
    - id: out
      producer: harness
      path: artifacts/out.json
      media_type: application/json
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: out
      target: artifacts/out.json
  output:
    format: json
"""


_P1_BINDINGS = {
    "p1": {
        "executor": "acp",
        "model": "entry-default",
        "extensions": [{"plugin": "acp", "options": {"entry": "codex"}}],
    }
}


def _lock(pkg: Path):
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg,
        "iso-test",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=_P1_BINDINGS,
    )


def test_valid_agent_isolation_locks(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path / "pkg", _BASE)
    lock = _lock(pkg)
    provider = thaw(lock.provider)
    topo = parse_logical_topology(provider, profile_ids={"p1"})
    assert topo is not None
    assert topo.mode == IsolationMode.SHARED_CONTAINER
    assert topo.actors[0].actor_id == "a1"
    assert "workspace/team" in topo.actors[0].shared_write
    # No physical fields in lock payload.
    blob = str(lock.canonical_payload())
    for bad in ("container_id", "uid", "docker_sock", "socket_path"):
        assert bad not in blob


def test_unknown_profile_in_actor_fail_closed(tmp_path: Path) -> None:
    bad = _BASE.replace("profiles: [p1]", "profiles: [missing-profile]")
    pkg = _write_pkg(tmp_path / "pkg", bad)
    with pytest.raises(ConfigError) as ei:
        _lock(pkg)
    assert ei.value.error_code in {"unknown_profile", "invalid_schema"}


def test_duplicate_actor_fail_closed(tmp_path: Path) -> None:
    bad = _BASE.replace(
        """        actors:
          - id: a1
            profiles: [p1]
""",
        """        actors:
          - id: a1
            profiles: [p1]
          - id: a1
            profiles: [p1]
""",
    )
    pkg = _write_pkg(tmp_path / "pkg", bad)
    with pytest.raises(ConfigError):
        _lock(pkg)


def test_shared_write_absolute_rejected(tmp_path: Path) -> None:
    bad = _BASE.replace("shared_write: [workspace/team]", "shared_write: [/etc/passwd]")
    pkg = _write_pkg(tmp_path / "pkg", bad)
    with pytest.raises(ConfigError):
        _lock(pkg)


def test_shared_write_dotdot_rejected(tmp_path: Path) -> None:
    bad = _BASE.replace("shared_write: [workspace/team]", "shared_write: [../outside]")
    pkg = _write_pkg(tmp_path / "pkg", bad)
    with pytest.raises(ConfigError):
        _lock(pkg)


def test_physical_field_forbidden(tmp_path: Path) -> None:
    bad = _BASE.replace(
        "mode: shared-container",
        "mode: shared-container\n    container_id: abc123",
    )
    pkg = _write_pkg(tmp_path / "pkg", bad)
    with pytest.raises(ConfigError) as ei:
        _lock(pkg)
    assert "forbidden" in str(ei.value).lower() or "physical" in str(ei.value).lower()


def test_implicit_topology_single_actor() -> None:
    provider = {"kind": "docker", "network": "bridge"}
    topo = parse_logical_topology(provider, profile_ids={"p1"}, implicit_profiles=["p1"])
    assert topo is not None
    assert len(topo.actors) == 1
    assert topo.actors[0].actor_id == "default"
