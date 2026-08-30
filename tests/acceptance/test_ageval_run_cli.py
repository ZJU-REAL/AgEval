"""Public ``ageval run``: an offline or broken Attempt never claims PASS."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "examples" / "datasets" / "minimal-demo"
TASK = "terminal-jsonl-agg"


def _ageval(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    # The automated suite stays bounded; the real Agent path is the public smoke.
    env = {**os.environ, "AGEVAL_OFFLINE_AGENT": "1"}
    # Locators must exist for lock; values are never used under AGEVAL_OFFLINE_AGENT.
    env.setdefault("ZHIPU_API_KEY", "ci-offline-placeholder")
    return subprocess.run(
        [sys.executable, "-m", "ageval.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO),
        env=env,
        timeout=180,
    )


def _dataset(tmp_path: Path) -> Path:
    """A copy of examples/datasets/minimal-demo, so evidence never lands in the checkout."""
    return Path(
        shutil.copytree(CORE, tmp_path / "minimal-demo", ignore=shutil.ignore_patterns(".ageval", ".env"))
    )


def test_offline_run_fails_closed(tmp_path: Path) -> None:
    result = _ageval("run", str(_dataset(tmp_path)), "--task", TASK)

    assert result.returncode != 0, result.stdout
    document = json.loads(result.stdout)
    assert document["status"] in {"ERROR", "FAIL"}
    assert document["score"] in (None, 0, 0.0)
    assert document["agent_invocations"] == 0


def test_unknown_task_is_one_error_on_stderr() -> None:
    result = _ageval("run", str(CORE), "--task", "does-not-exist")
    assert result.returncode == 2
    assert "unknown_task" in result.stderr
    assert result.stdout.strip() == ""
