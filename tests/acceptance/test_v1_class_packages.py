"""v1-class public packages: offline never silent PASS; campaign matrix digests differ."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run(
    args: list[str], *, offline: bool = False, extra_env: dict | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if offline:
        env["BORA_OFFLINE_AGENT"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=180,
    )


def test_offline_v1_class_packages_not_pass() -> None:
    db = REPO / "examples" / "journeys"
    for task in (
        "tau2-dialog-min",
        "multiagent-env-min",
        "terminal-jsonl-agg",
    ):
        r = _run(["run", str(db), "--task", task], offline=True)
        assert r.returncode != 0, task
        data = json.loads(r.stdout)
        assert data["status"] != "PASS", task


def test_campaign_matrix_two_digests() -> None:
    r = _run(
        [
            "campaign",
            str(REPO / "examples" / "core"),
            "--task",
            "sdk-tool-guard",
            "--matrix",
            "/parameters/seed=[1,2]",
        ]
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    data = json.loads(r.stdout)
    assert data["all_pass"] is True
    assert data["trial_count"] == 2
    digests = {t["digest"] for t in data["trials"]}
    assert len(digests) == 2
