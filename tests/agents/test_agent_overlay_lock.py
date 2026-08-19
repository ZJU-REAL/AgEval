"""Lock overlay resolve root follows agent_ref (design/14)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from bora.adapters.package_fs import LocalPackageReader
from bora.agents import store
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw


@pytest.fixture(autouse=True)
def _bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    monkeypatch.setenv("BORA_HOME", str(home))
    return home


def _write_database(tmp: Path, *, overlay_files: dict[str, str] | None = None) -> Path:
    db = tmp / "db"
    (db / "tasks" / "t").mkdir(parents=True)
    (db / "bora.yaml").write_text(
        "format: bora.database/1\ndatabase_id: example/overlays\nversion: '0.1.0'\n"
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    (db / "profiles.yaml").write_text(
        "format: bora.profiles/1\nbindings:\n  solver:\n    executor: mock\n    model: none\n",
        encoding="utf-8",
    )
    task = db / "tasks" / "t"
    (task / "harness.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (task / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    (task / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "format": "bora.task/1",
                "task_id": "t",
                "harness": {"runtime": "python", "entrypoint": "harness:run"},
                "parameters": {"models": {"default": "solver"}},
                "provider": {"kind": "local", "assurance": "l0"},
                "agent_profiles": [{"id": "solver"}, {"id": "user"}],
                "limits": {
                    "wall_time_seconds": 60,
                    "agent_invocations": 1,
                    "environment_actions": 0,
                },
                "artifacts": {"publishable": []},
                "evaluation": {
                    "runtime": "python",
                    "entrypoint": "evaluator:evaluate",
                    "network": "none",
                    "inputs": [],
                    "output": {"format": "json"},
                },
            }
        ),
        encoding="utf-8",
    )
    for rel, text in (overlay_files or {}).items():
        path = db / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return db


def _make_agent(
    tmp: Path,
    *,
    agent_id: str,
    version: str = "0.1.0",
    overlays: dict[str, str] | None = None,
    listed: list[str] | None = None,
) -> Path:
    pkg = tmp / f"agent-{agent_id.replace('/', '-')}"
    pkg.mkdir(parents=True)
    binding: dict[str, Any] = {"executor": "mock", "model": "none"}
    if listed:
        binding["overlays"] = listed
    (pkg / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "format": "bora.agent/1",
                "agent_id": agent_id.rsplit("/", 1)[-1],
                "version": version,
                "binding": binding,
            }
        ),
        encoding="utf-8",
    )
    for rel, text in (overlays or {}).items():
        path = pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return pkg


def _lock(db: Path, bindings: dict[str, dict[str, Any]]):
    core = ConfigCore(package_reader=LocalPackageReader())
    return core.load_and_lock(
        db / "tasks" / "t",
        "t",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=bindings,
    )


def test_lock_with_agent_ref_uses_agent_cache_not_dataset(tmp_path: Path) -> None:
    pkg = _make_agent(
        tmp_path,
        agent_id="official/xx",
        overlays={"overlays/skills/demo/SKILL.md": "# demo\n"},
        listed=["overlays/skills/demo"],
    )
    entry = store.install_from_path(pkg, agent_id="official/xx")
    db = _write_database(tmp_path)
    short = entry.digest[len("sha256:") :][:12]
    locked = _lock(
        db,
        {
            "*": {
                "executor": "mock",
                "model": "none",
                "overlays": ["overlays/skills/demo"],
                "agent_ref": f"official/xx@0.1.0+sha256:{short}",
            }
        },
    )
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["overlays"] == ["overlays/skills/demo"]
    assert (db / "overlays").exists() is False


def test_lock_agent_ref_ignores_dataset_same_path(tmp_path: Path) -> None:
    pkg = _make_agent(tmp_path, agent_id="official/xx")
    entry = store.install_from_path(pkg, agent_id="official/xx")
    db = _write_database(
        tmp_path,
        overlay_files={"overlays/skills/demo/SKILL.md": "# dataset copy\n"},
    )
    short = entry.digest[len("sha256:") :][:12]
    with pytest.raises(ConfigError) as ei:
        _lock(
            db,
            {
                "solver": {
                    "executor": "mock",
                    "model": "none",
                    "overlays": ["overlays/skills/demo"],
                    "agent_ref": f"official/xx@0.1.0+sha256:{short}",
                }
            },
        )
    assert ei.value.error_code == "missing_reference"


def test_lock_exact_role_without_overlays_not_attributed(tmp_path: Path) -> None:
    xx = _make_agent(
        tmp_path,
        agent_id="official/xx",
        overlays={"overlays/skills/demo/SKILL.md": "# demo\n"},
        listed=["overlays/skills/demo"],
    )
    yy = _make_agent(tmp_path, agent_id="official/yy")
    xx_entry = store.install_from_path(xx, agent_id="official/xx")
    yy_entry = store.install_from_path(yy, agent_id="official/yy")
    db = _write_database(tmp_path)
    xx_short = xx_entry.digest[len("sha256:") :][:12]
    yy_short = yy_entry.digest[len("sha256:") :][:12]
    locked = _lock(
        db,
        {
            "*": {
                "executor": "mock",
                "model": "none",
                "overlays": ["overlays/skills/demo"],
                "agent_ref": f"official/xx@0.1.0+sha256:{xx_short}",
            },
            "user": {
                "executor": "mock",
                "model": "none",
                "agent_ref": f"official/yy@0.1.0+sha256:{yy_short}",
            },
        },
    )
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["overlays"] == ["overlays/skills/demo"]
    assert overlay["bindings"]["solver"]["agent_ref"].startswith("official/xx@")
    assert "overlays" not in overlay["bindings"]["user"]
    assert overlay["bindings"]["user"]["agent_ref"].startswith("official/yy@")


def test_handwritten_profiles_still_use_database_root(tmp_path: Path) -> None:
    db = _write_database(
        tmp_path,
        overlay_files={"overlays/AGENTS.md": "# hello\n"},
    )
    locked = _lock(
        db,
        {
            "solver": {
                "executor": "mock",
                "model": "none",
                "overlays": ["overlays/AGENTS.md"],
            },
            "user": {"executor": "mock", "model": "none"},
        },
    )
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["overlays"] == ["overlays/AGENTS.md"]
    assert "overlays" not in overlay["bindings"]["user"]
