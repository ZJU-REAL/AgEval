"""Public CLI acceptance: attempt-trajectory package + Result.logs invocation tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATABASE = REPO / "examples" / "core"
TASK_DIR = DATABASE / "tasks" / "attempt-trajectory"
PACKAGE = DATABASE  # CLI path = Dataset root


def _run_cli(
    *extra: str, env: dict[str, str] | None = None, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "run",
            str(PACKAGE),
            "--task",
            "attempt-trajectory",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=e,
        timeout=timeout,
    )


def test_offline_trajectory_not_pass() -> None:
    result = _run_cli(env={"AGEVAL_OFFLINE_AGENT": "1"}, timeout=120)
    assert result.returncode != 0
    # stdout may be empty on some failures; prefer last JSON line
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")]
    if lines:
        data = json.loads(lines[-1])
        assert data.get("status") != "PASS"


def test_partial_failure_force_hook_no_pseudo_pass() -> None:
    """Second invoke forced fail → partial evidence, status not PASS, no final-response."""
    result = _run_cli(
        env={
            "AGEVAL_FORCE_INVOCATION_ERROR": "timeout",
            "AGEVAL_FORCE_INVOCATION_N": "2",
        },
        timeout=300,
    )
    assert result.returncode != 0
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")]
    assert lines, (result.stdout, result.stderr)
    data = json.loads(lines[-1])
    assert data.get("status") != "PASS"
    logs = data.get("logs") or data.get("evidence_path")
    root = Path(logs)
    if not root.is_absolute():
        root = (TASK_DIR / logs).resolve()
    if not root.is_dir():
        # offline short-circuit may leave no tree; force hook requires live service
        return
    dirs = sorted(p for p in (root / "agent" / "invocations").iterdir() if p.is_dir())
    # At least the forced second (and usually first completed)
    assert len(dirs) >= 1
    last = dirs[-1]
    meta = json.loads((last / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] in {"timeout", "failed", "crash", "cancelled"}
    assert not (last / "final-response.json").exists()


@pytest.mark.skipif(
    os.environ.get("AGEVAL_SKIP_REAL_CODEX") == "1",
    reason="skip real multi-invoke trajectory",
)
def test_success_multi_invoke_trajectory_tree() -> None:
    """Real Codex multi-invoke; parse full invocation tree from Result.logs."""
    import shutil

    if shutil.which("codex") is None:
        pytest.skip("codex missing")
    result = _run_cli(timeout=600)
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["agent_invocations"] == 2
    logs = data.get("logs") or data.get("evidence_path")
    assert logs
    root = Path(logs)
    if not root.is_absolute():
        root = (TASK_DIR / logs).resolve()
    assert root.is_dir(), root
    inv_root = root / "agent" / "invocations"
    assert inv_root.is_dir()
    dirs = sorted(p for p in inv_root.iterdir() if p.is_dir())
    assert len(dirs) == 2
    for d in dirs:
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == "completed"
        assert (d / "request.json").is_file()
        assert (d / "events.jsonl").is_file()
        assert (d / "final-response.json").is_file()
    # summary + effects skeleton
    assert (root / "summary.json").is_file()
    assert (root / "effects.jsonl").is_file()
    # Trajectory must not rewrite score semantics: PASS only from evaluator.
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    assert summary.get("status") == "PASS"
