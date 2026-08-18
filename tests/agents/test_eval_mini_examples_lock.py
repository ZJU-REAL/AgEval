"""Eval-mini example Databases lock offline (mock default binding + --agent lane)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("examples/scienceqa-mini", "sqa-photosynthesis"),
    ("examples/alfworld-mini", "alf-drawer-key"),
    ("examples/webshop-mini", "ws-tshirt"),
]


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "bora-home"
    home.mkdir()
    return {
        **os.environ,
        "BORA_HOME": str(home),
        "BORA_OFFLINE_AGENT": "1",
        "BORA_SKIP_DOCKER": "1",
    }


def _lock(env: dict[str, str], db: str, task: str, *extra: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "lock", str(ROOT / db), "--task", task, *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"{db}/{task}: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.mark.parametrize(("db", "task"), CASES)
def test_lock_with_database_profiles(env: dict[str, str], db: str, task: str) -> None:
    summary = _lock(env, db, task)
    binding = summary["job_overlay"]["bindings"]["solver"]
    assert binding["executor"] == "mock"


@pytest.mark.parametrize(("db", "task"), CASES)
def test_lock_with_example_agent(env: dict[str, str], db: str, task: str) -> None:
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "agent",
            "install",
            str(ROOT / "examples/agents/cc-default"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert install.returncode == 0, install.stderr
    summary = _lock(env, db, task, "--agent", "local/cc-default@0.1.0")
    binding = summary["job_overlay"]["bindings"]["solver"]
    assert binding["agent_ref"].startswith("local/cc-default@0.1.0+sha256:")
    assert binding["executor"] == "acp"
