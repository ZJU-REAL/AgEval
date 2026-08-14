"""Spec 00: bora lock writes per-profile extension_bindings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _chain_plugins(bindings: dict, slot: str) -> set[str]:
    row = bindings.get(slot) or {}
    return {str(item.get("plugin")) for item in (row.get("chain") or [])}


def _lock(*args: str) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "lock",
            str(ROOT / "examples/journeys"),
            "--task",
            "terminal-jsonl-agg",
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def test_lock_cli_extension_bindings_solver_acp() -> None:
    data = _lock()
    bindings = data["extension_bindings"]
    assert "solver" in bindings
    assert bindings["solver"]["executor"]["plugin"] == "acp"
    assert bindings["solver"]["executor"]["source"] == "profile_executor_field"
    assert bindings["solver"]["executor"]["kind"] == "provide"
    assert bindings["solver"]["before_agent_invoke"]["kind"] == "on"
    assert any(e.get("pointer") == "/extension_bindings" for e in data.get("resolution") or [])
    assert "dsh" not in _chain_plugins(bindings["solver"], "image_contribute")
    assert "nooa" not in _chain_plugins(bindings["solver"], "image_contribute")


def _installed_plugin_ids() -> set[str]:
    from bora.plugins.store import list_installed

    return {entry.plugin_id for entry in list_installed()}


def test_lock_dsh_profile_selects_dsh_not_nooa() -> None:
    ids = _installed_plugin_ids()
    if "dsh" not in ids or "nooa" not in ids:
        pytest.skip("path-install dsh and nooa to lock the journeys dsh profile")
    data = _lock("--profiles", str(ROOT / "examples/journeys/profiles.dsh.yaml"))
    solver = data["extension_bindings"]["solver"]
    assert solver["executor"]["plugin"] == "dsh"
    contribute = _chain_plugins(solver, "image_contribute")
    collect = _chain_plugins(solver, "trajectory_collect")
    assert "dsh" in contribute
    assert "dsh" in collect
    assert "nooa" not in contribute
    assert "nooa" not in collect
