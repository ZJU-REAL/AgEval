"""Config lock surface for executor: acp + options.entry (#59 bindings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw


def _write_pkg(root: Path, slot_ids: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    doc = {
        "format": "bora.task/1",
        "task_id": "acp-lock-test",
        "harness": {"runtime": "python", "entrypoint": "harness:run"},
        "parameters": {},
        "provider": {"kind": "local", "assurance": "l0"},
        "agent_profiles": [{"id": s} for s in slot_ids],
        "limits": {
            "wall_time_seconds": 60,
            "agent_invocations": 2,
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
    (root / "task.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (root / "harness.py").write_text("def run(ctx):\n    pass\n", encoding="utf-8")
    (root / "evaluator.py").write_text(
        "def evaluate(inputs):\n    return {'verdict': 'PASS'}\n", encoding="utf-8"
    )
    return root


def _lock(pkg: Path, bindings: dict[str, dict[str, Any]]):
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg,
        "acp-lock-test",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=bindings,
    )


def test_acp_profile_lock_snapshot(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path / "pkg", ["opencode-acp"])
    lock = _lock(
        pkg,
        {
            "opencode-acp": {
                "executor": "acp",
                "model": "entry-default",
                "options": {"entry": "opencode"},
            }
        },
    )
    profiles = thaw(lock.agent_profiles)
    assert profiles[0]["executor"] == "acp"
    assert profiles[0]["options"]["entry"] == "opencode"
    assert "_acp_lock" not in profiles[0]["options"]
    blob = str(profiles)
    assert "/opt/" not in blob
    assert "sk-" not in blob


def test_acp_missing_entry_fails(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path / "pkg", ["bad"])
    with pytest.raises(ConfigError):
        _lock(pkg, {"bad": {"executor": "acp", "model": "m", "options": {}}})


def test_acp_unknown_entry_fails(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path / "pkg", ["bad"])
    with pytest.raises(ConfigError):
        _lock(
            pkg,
            {
                "bad": {
                    "executor": "acp",
                    "model": "m",
                    "options": {"entry": "not-registered"},
                }
            },
        )


def test_acp_package_cannot_override_command(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path / "pkg", ["bad"])
    with pytest.raises(ConfigError, match="not package-overridable"):
        _lock(
            pkg,
            {
                "bad": {
                    "executor": "acp",
                    "model": "m",
                    "options": {"entry": "opencode", "command": ["evil"]},
                }
            },
        )
