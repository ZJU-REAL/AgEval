"""Public entrypoint acceptance: bora lock success / failure / determinism."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "core" / "config-minimal"
INVALID = REPO / "examples" / "core" / "config-invalid"


def _run_bora(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Prefer the installed console script when available; fall back to module.
    cmd = [sys.executable, "-m", "bora.cli.main", *args]
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO),
        env=env,
    )


def test_success_smoke() -> None:
    result = _run_bora("lock", str(MINIMAL), "--task", "config-minimal")
    assert result.returncode == 0, result.stderr
    assert result.stderr == "" or "warning" in result.stderr.lower()
    data = json.loads(result.stdout)
    assert data["task_id"] == "config-minimal"
    assert data["format"] == "bora.task/1"
    assert data["digest"].startswith("sha256:")
    assert "resolved_references" in data
    assert "resolution" in data
    # No host absolute package path leakage.
    assert str(MINIMAL.resolve()) not in result.stdout


def test_expected_failure_unknown_profile() -> None:
    result = _run_bora("lock", str(INVALID), "--task", "config-invalid")
    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "unknown_profile" in result.stderr
    # No successful .bora lock artifacts.
    assert not (INVALID / ".bora").exists()
    assert not (REPO / ".bora" / "locks").exists()


def test_determinism() -> None:
    r1 = _run_bora("lock", str(MINIMAL), "--task", "config-minimal")
    r2 = _run_bora("lock", str(MINIMAL), "--task", "config-minimal")
    assert r1.returncode == 0 and r2.returncode == 0
    assert r1.stdout == r2.stdout
    d1 = json.loads(r1.stdout)["digest"]
    d2 = json.loads(r2.stdout)["digest"]
    assert d1 == d2


def test_override_changes_digest() -> None:
    base = _run_bora("lock", str(MINIMAL), "--task", "config-minimal")
    over = _run_bora(
        "lock",
        str(MINIMAL),
        "--task",
        "config-minimal",
        "--set",
        "/parameters/seed=7",
    )
    assert base.returncode == 0 and over.returncode == 0
    b = json.loads(base.stdout)
    o = json.loads(over.stdout)
    assert b["digest"] != o["digest"]
    sources = [e.get("source") for e in o["resolution"]]
    assert "cli-override" in sources


def test_no_bora_artifacts_on_success(tmp_path: Path) -> None:
    result = _run_bora("lock", str(MINIMAL), "--task", "config-minimal", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".bora").exists()
    assert not (MINIMAL / ".bora").exists()


def test_no_task_local_import_on_lock() -> None:
    """Locking must not import package harness/evaluator modules."""
    # Run in a subprocess and inspect that examples were not imported as modules.
    code = f"""
import json, sys
from pathlib import Path
from bora.application.composition import build_lock_command
repo = Path({str(REPO)!r})
cmd = build_lock_command()
summary = cmd.run(package_root=repo / "examples" / "core" / "config-minimal", task_id="config-minimal")
assert summary["task_id"] == "config-minimal"
# harness.py is not a Python package import path under examples
assert not any("config-minimal" in m and m.endswith("harness") for m in sys.modules)
print(json.dumps({{"ok": True, "digest": summary["digest"]}}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"] is True
