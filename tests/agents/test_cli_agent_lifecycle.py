"""CLI: ageval agent install/list/show/uninstall + lock --agent acceptance (design/14)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_AGENT = ROOT / "examples/agents/pi-default"
DATABASE = ROOT / "examples/journeys"


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "ageval-home"
    home.mkdir()
    return {
        **os.environ,
        "AGEVAL_HOME": str(home),
        "AGEVAL_OFFLINE_AGENT": "1",
        "AGEVAL_SKIP_DOCKER": "1",
    }


def _cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ageval.cli.main", *args],
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
    assert data["ref"] == "local/pi-default@0.1.0"

    listed = json.loads(_cli(env, "agent", "list").stdout)
    assert [a["agent_id"] for a in listed["agents"]] == ["local/pi-default"]

    shown = json.loads(_cli(env, "agent", "show", "local/pi-default@0.1.0").stdout)
    assert shown["binding"]["executor"] == "acp"
    assert shown["digest"].startswith("sha256:")

    assert _cli(env, "agent", "uninstall", "local/pi-default").returncode == 0
    assert json.loads(_cli(env, "agent", "list").stdout)["agents"] == []


def test_agent_side_by_side_versions(env: dict[str, str], tmp_path: Path) -> None:
    def _pkg(version: str) -> Path:
        pkg = tmp_path / f"ag-{version}"
        pkg.mkdir()
        (pkg / "agent.yaml").write_text(
            f"format: ageval.agent/1\nagent_id: http-default\nversion: '{version}'\n"
            "label: T\nbinding: {executor: openai-http, model: none}\n",
            encoding="utf-8",
        )
        return pkg

    assert _cli(env, "agent", "install", str(_pkg("1.0.0"))).returncode == 0
    assert _cli(env, "agent", "install", str(_pkg("2.0.0"))).returncode == 0
    shown = json.loads(_cli(env, "agent", "show", "local/http-default").stdout)
    assert shown["version"] == "2.0.0"
    assert _cli(env, "agent", "uninstall", "local/http-default@1.0.0").returncode == 0
    listed = json.loads(_cli(env, "agent", "list").stdout)
    assert [a["version"] for a in listed["agents"]] == ["2.0.0"]
    assert _cli(env, "agent", "uninstall", "local/http-default").returncode == 0
    assert json.loads(_cli(env, "agent", "list").stdout)["agents"] == []


def test_agent_and_profiles_mutually_exclusive(env: dict[str, str]) -> None:
    proc = _cli(
        env,
        "lock",
        str(DATABASE),
        "--task",
        "terminal-jsonl-agg",
        "--agent",
        str(EXAMPLE_AGENT),
        "--profiles",
        str(DATABASE / "profiles.yaml"),
    )
    assert proc.returncode == 2
    assert "mutually exclusive" in proc.stderr


def _lock_summary(env: dict[str, str], *extra: str) -> dict[str, Any]:
    proc = _cli(env, "lock", str(DATABASE), "--task", "terminal-jsonl-agg", *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_lock_with_agent_records_agent_ref_and_matches_profiles_lane(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert _cli(env, "agent", "install", str(EXAMPLE_AGENT)).returncode == 0

    summary = _lock_summary(env, "--agent", "local/pi-default@0.1.0")
    agent_profiles = summary["job_overlay"]["agent_profiles"]
    refs = {row.get("agent_ref") for row in agent_profiles.values()}
    assert len(refs) == 1
    (ref,) = refs
    assert ref.startswith("local/pi-default@0.1.0+sha256:")

    # Same run twice → deterministic digest.
    again = _lock_summary(env, "--agent", "local/pi-default@0.1.0")
    assert again["digest"] == summary["digest"]

    # Equivalent hand-written profiles file (same agent_profiles incl. agent_ref)
    # must produce the identical lock digest — the lanes are the same lane.
    import yaml

    profiles_doc = {"format": "ageval.profiles/1", "agent_profiles": {}}
    for role, row in agent_profiles.items():
        clone = dict(row)
        api_key = clone.get("api_key")
        if isinstance(api_key, str) and api_key and not api_key.startswith("${"):
            clone["api_key"] = f"${{{api_key}}}"
        profiles_doc["agent_profiles"][role] = clone
    profiles_path = tmp_path / "equiv-profiles.yaml"
    profiles_path.write_text(yaml.safe_dump(profiles_doc, sort_keys=False), encoding="utf-8")

    via_profiles = _lock_summary(env, "--profiles", str(profiles_path))
    assert via_profiles["digest"] == summary["digest"]


def test_lock_model_override_requires_agent_and_writes_overlay(
    env: dict[str, str],
) -> None:
    assert _cli(env, "agent", "install", str(EXAMPLE_AGENT)).returncode == 0

    default = _lock_summary(env, "--agent", "local/pi-default@0.1.0")
    default_models = {row.get("model") for row in default["job_overlay"]["agent_profiles"].values()}
    assert default_models == {"entry-default"}

    overridden = _lock_summary(env, "--agent", "local/pi-default@0.1.0", "--model", "glm-4.7")
    overlay = overridden["job_overlay"]["agent_profiles"]
    assert {row.get("model") for row in overlay.values()} == {"glm-4.7"}
    assert overridden["digest"] != default["digest"]
    dumped = json.dumps(overridden)
    assert "glm-4.7" in dumped
    assert "sk-" not in dumped

    via_set = _lock_summary(
        env,
        "--agent",
        "local/pi-default@0.1.0",
        "--model",
        "glm-4.7",
        "--set",
        '/agent_profiles/solver/model="via-set"',
    )
    assert via_set["job_overlay"]["agent_profiles"]["solver"]["model"] == "via-set"

    missing = _cli(env, "lock", str(DATABASE), "--task", "terminal-jsonl-agg", "--model", "glm-4.7")
    assert missing.returncode == 2
    assert "invalid_override: --model requires --agent" in missing.stderr
