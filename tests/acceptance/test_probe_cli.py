"""Public entrypoint: bora lock|run --probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bora.plugins.store import install_from_path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "tests/fixtures/plugins/host-probe"
DB = ROOT / "tests/fixtures/databases/probe-min"
CORE = ROOT / "examples/core"
SECRET = "sk-cli-probe-secret"


@pytest.fixture()
def bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    install_from_path(PLUGIN)
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def _run_bora(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bora.cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=merged,
    )


def test_lock_without_probe_unchanged() -> None:
    r1 = _run_bora("lock", str(CORE), "--task", "config-minimal")
    r2 = _run_bora("lock", str(CORE), "--task", "config-minimal")
    assert r1.returncode == 0 and r2.returncode == 0
    assert r1.stdout == r2.stdout
    data = json.loads(r1.stdout)
    assert "probe" not in data


def test_lock_probe_core_minimal_ready() -> None:
    result = _run_bora("lock", str(CORE), "--task", "config-minimal", "--probe")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["probe"]["ready"] is True
    assert data["probe"]["path"] == "l0"
    assert data["digest"].startswith("sha256:")
    plain = _run_bora("lock", str(CORE), "--task", "config-minimal")
    assert json.loads(plain.stdout)["digest"] == data["digest"]


def test_lock_probe_l0_missing_import_exits_1(
    bora_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_bora(
        "lock",
        str(DB),
        "--task",
        "l0-task",
        "--probe",
        env={"BORA_HOME": str(bora_home), "BORA_OFFLINE_AGENT": "1"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["probe"]["ready"] is False
    assert data["probe"]["offline_agent"] is True
    assert any(c["id"] == "host_import" and not c["ok"] for c in data["probe"]["checks"])


def test_lock_probe_l1_without_host_import(
    bora_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del monkeypatch
    result = _run_bora(
        "lock",
        str(DB),
        "--task",
        "l1-task",
        "--probe",
        env={
            "BORA_HOME": str(bora_home),
            "BORA_SKIP_DOCKER": "0",
            "PROBE_API_KEY": SECRET,
        },
    )
    data = json.loads(result.stdout)
    assert data["probe"]["path"] == "l1"
    assert SECRET not in result.stdout
    assert not any(c["id"] == "host_import" for c in data["probe"]["checks"])
    bake = next(c for c in data["probe"]["checks"] if c["id"] == "l1_bake_declared")
    assert bake["ok"] is True
    # Docker may be down in CI; only assert bake + no secret + no host_import.


def test_run_probe_does_not_start_attempt(bora_home: Path) -> None:
    result = _run_bora(
        "run",
        str(DB),
        "--task",
        "l0-task",
        "--probe",
        env={"BORA_HOME": str(bora_home)},
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "probe" in data
    assert "status" not in data or data.get("probe")
    assert not (DB / ".bora" / "runs").exists()
