"""evaluation.placement / timeout on top of #133 tmpfs_mb."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.config.package_fs import LocalPackageReader
from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.errors import ConfigError
from ageval.config.eval_placement import (
    PLACEMENT_STAGING,
    PLACEMENT_WRITABLE,
    resolve_eval_placement,
)
from ageval.config.load_and_lock import ConfigCore


def test_defaults_staging() -> None:
    spec = resolve_eval_placement({"tmpfs_mb": 32})
    assert spec.mode == PLACEMENT_STAGING
    assert spec.timeout_seconds == 90.0
    assert spec.tmpfs_mb == 32
    assert spec.tmpfs_exec is False
    assert spec.network == "none"
    assert spec.tmpfs_spec == "/tmp:rw,noexec,nosuid,size=32m"


def test_network_omit_and_none_are_offline() -> None:
    assert resolve_eval_placement({"tmpfs_mb": 32}).network == "none"
    assert resolve_eval_placement({"network": "none", "tmpfs_mb": 32}).network == "none"


def test_network_bridge_accepted() -> None:
    spec = resolve_eval_placement({"network": "bridge", "tmpfs_mb": 32})
    assert spec.network == "bridge"


def test_bad_network() -> None:
    with pytest.raises(ConfigError, match="network") as ei:
        resolve_eval_placement({"network": "host", "tmpfs_mb": 32})
    assert ei.value.location == "/evaluation/network"


def test_reuse_attempt_omit_false_true() -> None:
    assert resolve_eval_placement({"tmpfs_mb": 32}).reuse_attempt is False
    assert resolve_eval_placement({"reuse_attempt": False, "tmpfs_mb": 32}).reuse_attempt is False
    assert resolve_eval_placement({"reuse_attempt": True, "tmpfs_mb": 32}).reuse_attempt is True


def test_bad_reuse_attempt() -> None:
    with pytest.raises(ConfigError, match="reuse_attempt") as ei:
        resolve_eval_placement({"reuse_attempt": "yes", "tmpfs_mb": 32})
    assert ei.value.location == "/evaluation/reuse_attempt"


def test_writable_keeps_declared_tmpfs() -> None:
    spec = resolve_eval_placement({"placement": "writable", "tmpfs_mb": 4096})
    assert spec.mode == PLACEMENT_WRITABLE
    assert spec.timeout_seconds == 300.0
    assert spec.tmpfs_mb == 4096
    assert spec.tmpfs_exec is True
    assert spec.tmpfs_spec == "/tmp:rw,exec,nosuid,size=4096m"


def test_timeout_capped_by_wall() -> None:
    with pytest.raises(ConfigError, match="exceeds cap"):
        resolve_eval_placement(
            {"placement": "writable", "timeout_seconds": 500, "tmpfs_mb": 256},
            wall_time_seconds=120,
        )


def test_default_timeout_clamped_to_wall() -> None:
    spec = resolve_eval_placement({"tmpfs_mb": 32}, wall_time_seconds=60)
    assert spec.timeout_seconds == 60.0


def test_bad_placement() -> None:
    with pytest.raises(ConfigError, match="placement"):
        resolve_eval_placement({"placement": "jailbreak", "tmpfs_mb": 32})


_P1 = {
    "p1": {
        "executor": "acp",
        "model": "entry-default",
        "extensions": [{"plugin": "acp", "options": {"entry": "pi"}}],
    }
}


def _pkg(root: Path, extra: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "harness.py").write_text("def run(ctx): ...\n", encoding="utf-8")
    (root / "evaluator.py").write_text("def evaluate(ctx): ...\n", encoding="utf-8")
    env = root / "environment"
    env.mkdir(parents=True, exist_ok=True)
    (env / "Dockerfile").write_text("FROM ageval-attempt:l1\n", encoding="utf-8")
    (root / "task.yaml").write_text(
        f"""
format: ageval.task/1
task_id: eval-place

harness:
  runtime: python
  entrypoint: harness:run

parameters: {{}}

provider:
  kind: docker
  assurance: l1

agent_profiles:
  - id: p1

limits:
  wall_time_seconds: 600
  agent_invocations: 1
  environment_actions: 0

artifacts:
  publishable: []

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
{extra}
  inputs: []
  output:
    format: json
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_lock_accepts_writable_with_tmpfs(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  placement: writable\n  timeout_seconds: 180\n  tmpfs_mb: 4096")
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "eval-place",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=_P1,
    )
    ev = dict(locked.evaluation)
    assert ev.get("placement") == "writable"
    assert ev.get("timeout_seconds") == 180
    assert ev.get("tmpfs_mb") == 4096


def test_lock_omits_network(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  tmpfs_mb: 32")
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "eval-place",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=_P1,
    )
    ev = dict(locked.evaluation)
    assert "network" not in ev or ev.get("network") is None


def test_lock_accepts_network_bridge(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  network: bridge\n  tmpfs_mb: 32")
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "eval-place",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=_P1,
    )
    assert dict(locked.evaluation).get("network") == "bridge"


def test_lock_accepts_reuse_attempt(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  reuse_attempt: true\n  tmpfs_mb: 32")
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "eval-place",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=_P1,
    )
    assert dict(locked.evaluation).get("reuse_attempt") is True


def test_lock_rejects_invalid_reuse_attempt(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  reuse_attempt: maybe")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError, match="reuse_attempt") as ei:
        core.load_and_lock(
            pkg,
            "eval-place",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings=_P1,
        )
    assert ei.value.location == "/evaluation/reuse_attempt"


def test_lock_rejects_unknown_network(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  network: host")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError, match="network") as ei:
        core.load_and_lock(
            pkg,
            "eval-place",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings=_P1,
        )
    assert ei.value.location == "/evaluation/network"


def test_lock_rejects_timeout_over_wall(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _pkg(pkg, "  placement: writable\n  timeout_seconds: 900\n  tmpfs_mb: 256")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError, match="timeout_seconds"):
        core.load_and_lock(
            pkg,
            "eval-place",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings=_P1,
        )
