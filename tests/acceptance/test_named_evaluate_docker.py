"""Real docker: named evaluate hosts start lazily; unused image is not built."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ageval.plugins.contrib.docker.images import daemon_available

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "datasets" / "eval-named-min"


def _skip_without_docker() -> None:
    if os.environ.get("AGEVAL_SKIP_DOCKER") == "1":
        pytest.skip("AGEVAL_SKIP_DOCKER=1")
    if not daemon_available():
        pytest.skip("docker daemon is not reachable")


def _ageval(env: dict[str, str], *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ageval.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=900,
    )


def _run_dir(dataset: Path, result: dict[str, object]) -> Path:
    logs = str(result.get("logs") or result.get("evidence_path") or "")
    root = dataset / logs if logs else dataset / ".ageval" / "runs"
    if root.is_file():
        return root.parent
    if (root / "result.json").is_file():
        return root
    runs = dataset / ".ageval" / "runs"
    found = sorted(p for p in runs.rglob("result.json"))
    assert found, f"no result.json under {runs}"
    return found[-1].parent


def test_named_evaluate_execs_only_the_first_host(tmp_path: Path) -> None:
    _skip_without_docker()
    dataset = Path(
        shutil.copytree(
            FIXTURE,
            tmp_path / "eval-named",
            ignore=shutil.ignore_patterns(".ageval"),
        )
    )
    env = os.environ.copy()
    env.pop("AGEVAL_OFFLINE_AGENT", None)
    ran = _ageval(env, "run", str(dataset), "--task", "publish-tree", cwd=dataset)
    assert ran.returncode == 0, ran.stderr or ran.stdout
    result = json.loads(ran.stdout)
    assert result["status"] == "PASS"
    metrics = result.get("metrics") or {}
    assert metrics.get("answer") == "42"
    assert metrics.get("expected") == "42"
    assert metrics.get("leaked") is False

    run_dir = _run_dir(dataset, result)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    facts = summary.get("facts") or result.get("facts") or []
    started = [
        item.get("detail") or {}
        for item in facts
        if isinstance(item, dict) and item.get("name") == "evaluate_host_started"
    ]
    assert [row.get("name") for row in started] == ["audit"]
    names = {str(item.get("name")) for item in facts if isinstance(item, dict)}
    assert "evaluate_exec" in names
    assert "evaluate_host_stopped" in names
    assert "environment_stopped" in names
    assert not (run_dir / "evaluation" / "observation.jsonl").exists()
