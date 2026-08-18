"""CLI: bora agent install/list/show/uninstall + lock --agent acceptance (design/14)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_AGENT = ROOT / "examples/agents/mock-default"
DATABASE = ROOT / "examples/core"


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


def _cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_agent_install_list_show_uninstall(env: dict[str, str]) -> None:
    proc = _cli(env, "agent", "install", str(EXAMPLE_AGENT))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["ref"] == "local/mock-default@0.1.0"

    listed = json.loads(_cli(env, "agent", "list").stdout)
    assert [a["agent_id"] for a in listed["agents"]] == ["local/mock-default"]

    shown = json.loads(_cli(env, "agent", "show", "local/mock-default@0.1.0").stdout)
    assert shown["binding"]["executor"] == "mock"
    assert shown["digest"].startswith("sha256:")

    assert _cli(env, "agent", "uninstall", "local/mock-default").returncode == 0
    assert json.loads(_cli(env, "agent", "list").stdout)["agents"] == []


def test_agent_and_profiles_mutually_exclusive(env: dict[str, str]) -> None:
    proc = _cli(
        env,
        "lock",
        str(DATABASE),
        "--task",
        "sdk-agent-session",
        "--agent",
        str(EXAMPLE_AGENT),
        "--profiles",
        str(DATABASE / "profiles.yaml"),
    )
    assert proc.returncode == 2
    assert "mutually exclusive" in proc.stderr


def _lock_summary(env: dict[str, str], *extra: str) -> dict[str, Any]:
    proc = _cli(env, "lock", str(DATABASE), "--task", "sdk-agent-session", *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_lock_with_agent_records_agent_ref_and_matches_profiles_lane(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert _cli(env, "agent", "install", str(EXAMPLE_AGENT)).returncode == 0

    summary = _lock_summary(env, "--agent", "local/mock-default@0.1.0")
    bindings = summary["job_overlay"]["bindings"]
    refs = {row.get("agent_ref") for row in bindings.values()}
    assert len(refs) == 1
    (ref,) = refs
    assert ref.startswith("local/mock-default@0.1.0+sha256:")

    # Same run twice → deterministic digest.
    again = _lock_summary(env, "--agent", "local/mock-default@0.1.0")
    assert again["digest"] == summary["digest"]

    # Equivalent hand-written profiles file (same bindings incl. agent_ref)
    # must produce the identical lock digest — the lanes are the same lane.
    import yaml

    profiles_doc = {"format": "bora.profiles/1", "bindings": {}}
    for role, row in bindings.items():
        clone = dict(row)
        api_key = clone.get("api_key")
        if isinstance(api_key, str) and api_key and not api_key.startswith("${"):
            clone["api_key"] = f"${{{api_key}}}"
        profiles_doc["bindings"][role] = clone
    profiles_path = tmp_path / "equiv-profiles.yaml"
    profiles_path.write_text(yaml.safe_dump(profiles_doc, sort_keys=False), encoding="utf-8")

    via_profiles = _lock_summary(env, "--profiles", str(profiles_path))
    assert via_profiles["digest"] == summary["digest"]
