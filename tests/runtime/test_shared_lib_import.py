"""Harness / evaluator can import modules from Dataset shared/lib (#65)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.application.run_command_evaluator import run_evaluator_worker
from bora.application.run_harness import run_harness_package
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore


def _scaffold(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bora.yaml").write_text(
        "format: bora.database/1\n"
        "database_id: test/shared-import\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    shared_lib = root / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge_mod.py").write_text(
        "TOKEN = 'from-shared'\n",
        encoding="utf-8",
    )
    task = root / "tasks" / "t1"
    task.mkdir(parents=True)
    (task / "task.yaml").write_text(
        """format: bora.task/1
task_id: t1
harness:
  runtime: python
  entrypoint: harness:run
provider:
  kind: local
  assurance: l0
agent_profiles: []
limits:
  wall_time_seconds: 60
  agent_invocations: 0
  environment_actions: 0
artifacts:
  publishable:
    - id: session-output
      producer: harness
      path: artifacts/session-output.json
      media_type: application/json
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: session-output
      target: artifacts/session-output.json
  output:
    format: json
""",
        encoding="utf-8",
    )
    (task / "harness.py").write_text(
        """
from bora_sdk.terminal import HarnessTerminal

def run(ctx):
    import bridge_mod
    ctx.publish_json("session-output", {"token": bridge_mod.TOKEN})
    return HarnessTerminal.completed()
""",
        encoding="utf-8",
    )
    (task / "evaluator.py").write_text(
        """
def evaluate(payload):
    import bridge_mod
    arts = payload.get("artifacts") or {}
    # token path not required; import success is the gate
    return {
        "status": "PASS" if bridge_mod.TOKEN == "from-shared" else "FAIL",
        "score": 1.0 if bridge_mod.TOKEN == "from-shared" else 0.0,
        "metrics": {"token": bridge_mod.TOKEN},
    }
""",
        encoding="utf-8",
    )
    return task


@pytest.mark.asyncio
async def test_harness_imports_shared_lib(tmp_path: Path) -> None:
    task = _scaffold(tmp_path)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    result = await run_harness_package(lock, task, timeout_seconds=20.0, database_root=tmp_path)
    env = result["envelope"]
    assert env.get("ok") is True, env
    published = env.get("published") or {}
    assert "session-output" in published
    text = Path(published["session-output"]).read_text(encoding="utf-8")
    assert "from-shared" in text


def test_evaluator_imports_shared_lib(tmp_path: Path) -> None:
    task = _scaffold(tmp_path)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    # Minimal artifact file for evaluate inputs
    art = tmp_path / "session-output.json"
    art.write_text('{"token":"x"}\n', encoding="utf-8")
    raw = run_evaluator_worker(
        task,
        lock,
        {"session-output": str(art)},
        database_root=tmp_path,
    )
    assert raw.get("status") == "PASS"
    assert (raw.get("metrics") or {}).get("token") == "from-shared"
