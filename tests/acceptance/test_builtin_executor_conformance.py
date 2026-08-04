"""Public CLI: profile-only switch across codex / pi / opencode."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "examples" / "core" / "builtin-executor-conformance"


def _run(profile: str, *, env: dict[str, str] | None = None, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    if env:
        e.update(env)
    # Override active profile via lock override if supported; else env for harness params.
    # run_command uses lock parameters — use --set if CLI supports it.
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(PACKAGE),
            "--task",
            "builtin-executor-conformance",
            "--set",
            f'/parameters/active_profile="{profile}"',
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=e,
        timeout=timeout,
    )


def test_unknown_executor_fail_closed() -> None:
    # Force unknown via profile override is hard; unit registry covers KeyError.
    # Offline never PASS.
    result = _run("codex-mini", env={"BORA_OFFLINE_AGENT": "1"}, timeout=120)
    assert result.returncode != 0
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")]
    if lines:
        assert json.loads(lines[-1]).get("status") != "PASS"


@pytest.mark.skipif(os.environ.get("BORA_SKIP_REAL_CODEX") == "1", reason="skip real")
def test_codex_profile_success() -> None:
    if shutil.which("codex") is None:
        pytest.skip("codex missing")
    result = _run("codex-mini", timeout=300)
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    root = Path(data["logs"])
    assert (root / "agent" / "invocations").is_dir()
    dirs = list((root / "agent" / "invocations").iterdir())
    assert len(dirs) == 1
    meta = json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert meta["executor_kind"] == "codex"


@pytest.mark.skipif(shutil.which("pi") is None, reason="pi missing")
def test_pi_profile_success() -> None:
    if os.environ.get("BORA_SKIP_REAL_PI") == "1":
        pytest.skip("skip real pi")
    result = _run("pi-mini", timeout=300)
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    root = Path(data["logs"])
    dirs = list((root / "agent" / "invocations").iterdir())
    assert len(dirs) == 1
    meta = json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert meta["executor_kind"] == "pi"


@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode missing")
def test_opencode_profile_success() -> None:
    if os.environ.get("BORA_SKIP_REAL_OPENCODE") == "1":
        pytest.skip("skip real opencode")
    result = _run("opencode-mini", timeout=300)
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    root = Path(data["logs"])
    dirs = list((root / "agent" / "invocations").iterdir())
    assert len(dirs) == 1
    meta = json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert meta["executor_kind"] == "opencode"


@pytest.mark.skipif(
    shutil.which("codex") is None or shutil.which("pi") is None,
    reason="need codex+pi",
)
def test_mixed_profile_independent_trees() -> None:
    if os.environ.get("BORA_SKIP_REAL_CODEX") == "1":
        pytest.skip("skip real")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples" / "core" / "builtin-executor-mixed"),
            "--task",
            "builtin-executor-mixed",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=480,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["agent_invocations"] == 2
    root = Path(data["logs"])
    dirs = sorted(p for p in (root / "agent" / "invocations").iterdir() if p.is_dir())
    kinds = [
        json.loads((d / "metadata.json").read_text(encoding="utf-8"))["executor_kind"]
        for d in dirs
    ]
    assert kinds == ["codex", "pi"]
