"""Public ``ageval run``: an offline or broken Attempt never claims PASS."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "examples" / "core"
TASK = "acp-local-min"


def _ageval(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    # The automated suite stays bounded; the real Agent path is the public smoke.
    env = {**os.environ, "AGEVAL_OFFLINE_AGENT": "1"}
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
    """A copy of examples/core, so evidence never lands in the checkout."""
    return Path(shutil.copytree(CORE, tmp_path / "core", ignore=shutil.ignore_patterns(".ageval")))


def test_offline_run_fails_closed(tmp_path: Path) -> None:
    result = _ageval("run", str(_dataset(tmp_path)), "--task", TASK)

    assert result.returncode != 0, result.stdout
    document = json.loads(result.stdout)
    assert document["status"] in {"ERROR", "FAIL"}
    assert document["score"] in (None, 0, 0.0)
    assert document["agent_invocations"] == 0


def test_verdict_comes_from_the_evaluator_not_the_workspace(tmp_path: Path) -> None:
    """A pre-planted answer file is still judged; offline means the agent did not write it."""
    dataset = _dataset(tmp_path)
    seed = dataset / "tasks" / TASK / "data"
    seed.mkdir(parents=True, exist_ok=True)
    (seed / "answer.txt").write_text("42\n", encoding="utf-8")

    result = _ageval("run", str(dataset), "--task", TASK)

    document = json.loads(result.stdout)
    assert document["status"] != "ERROR", "the evaluator must run and decide"
    assert document["metrics"]["agent_ok"] is False


def test_unknown_task_is_one_error_on_stderr() -> None:
    result = _ageval("run", str(CORE), "--task", "does-not-exist")
    assert result.returncode == 2
    assert "unknown_task" in result.stderr
    assert result.stdout.strip() == ""
