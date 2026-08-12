"""Harness worker application acceptance (v0.5)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.application.run_harness import run_harness_package
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "examples" / "core" / "tasks" / "harness-minimal"


def _lock():
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        PKG, "harness-minimal", capabilities=DeclarationCapabilityCatalog()
    )


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@pytest.mark.asyncio
async def test_success_minimal() -> None:
    lock = _lock()
    result = await run_harness_package(lock, PKG, timeout_seconds=20.0)
    assert result["parent_imported_task"] is False
    env = result["envelope"]
    assert env["ok"] is True
    assert env["terminal"]["kind"] == "completed"
    assert "result" in env["published"]
    # completed is not PASS
    assert "PASS" not in str(env)
    assert result["writer_stop_confirmed"] is True
    assert result["process_terminal"] == "exited"


@pytest.mark.asyncio
async def test_missing_entrypoint(tmp_path: Path) -> None:
    # Copy package without harness entry function name mismatch via bad entrypoint lock override
    # Build a temporary package missing harness.py
    pkg = tmp_path / "bad"
    pkg.mkdir()
    (pkg / "task.yaml").write_text(
        (PKG / "task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    # harness.py missing → lock fails at Config with missing_reference
    from bora.config.errors import ConfigError

    with pytest.raises(ConfigError):
        ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
            pkg, "harness-minimal", capabilities=DeclarationCapabilityCatalog()
        )


@pytest.mark.asyncio
async def test_import_failure(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    yaml = (PKG / "task.yaml").read_text(encoding="utf-8")
    (pkg / "task.yaml").write_text(yaml, encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    (pkg / "harness.py").write_text("raise RuntimeError('boom-import')\n", encoding="utf-8")
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg, "harness-minimal", capabilities=DeclarationCapabilityCatalog()
    )
    result = await run_harness_package(lock, pkg, timeout_seconds=20.0)
    assert result["envelope"]["ok"] is False
    assert result["parent_imported_task"] is False


@pytest.mark.asyncio
async def test_harness_reaps_same_group_grandchild(tmp_path: Path) -> None:
    """Worker may fork a same-group writer; Provider must confirm the group is dead."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    yaml = (PKG / "task.yaml").read_text(encoding="utf-8")
    yaml = yaml.replace("task_id: harness-minimal", "task_id: harness-grandchild")
    (pkg / "task.yaml").write_text(yaml, encoding="utf-8")
    (pkg / "evaluator.py").write_text(
        "def evaluate(inputs):\n    return {'status': 'PASS', 'metrics': {}}\n",
        encoding="utf-8",
    )
    (pkg / "harness.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import os",
                "import time",
                "from bora_sdk import HarnessContext, HarnessTerminal",
                "",
                "async def run(ctx: HarnessContext) -> HarnessTerminal:",
                "    pid = os.fork()",
                "    if pid == 0:",
                "        time.sleep(30)",
                "        os._exit(0)",
                "    time.sleep(0.1)",
                "    ctx.publish_json('result', {'grandchild_pid': pid})",
                "    return HarnessTerminal.completed('spawned-grandchild')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg, "harness-grandchild", capabilities=DeclarationCapabilityCatalog()
    )
    result = await run_harness_package(lock, pkg, timeout_seconds=20.0)
    assert result["envelope"]["ok"] is True
    pgid = result["pgid"]
    assert pgid is not None
    alive = _group_alive(int(pgid))
    assert result["writer_stop_confirmed"] is (not alive)
    assert result["writer_stop_confirmed"] is True
    assert alive is False
