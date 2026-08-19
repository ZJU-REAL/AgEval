"""Harness / evaluator import Dataset glue via shared.lib.* (#68)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ageval.config.package_fs import LocalPackageReader
from ageval.application.attempt.run_command_evaluator import run_evaluator_worker
from ageval.application.attempt.run_harness import run_harness_package
from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import freeze


def _scaffold(root: Path, *, with_task_lib: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ageval.yaml").write_text(
        "format: ageval.dataset/1\n"
        "dataset_id: test/shared-import\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    shared = root / "shared"
    shared_lib = shared / "lib"
    shared_lib.mkdir(parents=True)
    (shared / "__init__.py").write_text("", encoding="utf-8")
    (shared_lib / "__init__.py").write_text("", encoding="utf-8")
    (shared_lib / "bridge_mod.py").write_text(
        "TOKEN = 'from-shared'\n",
        encoding="utf-8",
    )
    task = root / "tasks" / "t1"
    task.mkdir(parents=True)
    (task / "task.yaml").write_text(
        """format: ageval.task/1
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
    if with_task_lib:
        lib = task / "lib"
        lib.mkdir()
        (lib / "__init__.py").write_text("", encoding="utf-8")
        # Same basename as shared module — must resolve via lib.* not shared.lib.*
        (lib / "bridge_mod.py").write_text(
            "TOKEN = 'from-task-lib'\n",
            encoding="utf-8",
        )
        harness_body = """
from ageval_sdk.terminal import RunTerminal
from lib.bridge_mod import TOKEN as TASK_TOKEN
from shared.lib.bridge_mod import TOKEN as SHARED_TOKEN

def run(ctx):
    ctx.publish_json(
        "session-output",
        {"task": TASK_TOKEN, "shared": SHARED_TOKEN},
    )
    return RunTerminal.completed()
"""
        eval_body = """
from lib.bridge_mod import TOKEN as TASK_TOKEN
from shared.lib.bridge_mod import TOKEN as SHARED_TOKEN

def evaluate(payload):
    ok = TASK_TOKEN == "from-task-lib" and SHARED_TOKEN == "from-shared"
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {"task": TASK_TOKEN, "shared": SHARED_TOKEN},
    }
"""
    else:
        harness_body = """
from ageval_sdk.terminal import RunTerminal
from shared.lib.bridge_mod import TOKEN

def run(ctx):
    ctx.publish_json("session-output", {"token": TOKEN})
    return RunTerminal.completed()
"""
        eval_body = """
from shared.lib.bridge_mod import TOKEN

def evaluate(payload):
    arts = payload.get("artifacts") or {}
    _ = arts
    return {
        "status": "PASS" if TOKEN == "from-shared" else "FAIL",
        "score": 1.0 if TOKEN == "from-shared" else 0.0,
        "metrics": {"token": TOKEN},
    }
"""
    (task / "harness.py").write_text(harness_body, encoding="utf-8")
    (task / "evaluator.py").write_text(eval_body, encoding="utf-8")
    return task


@pytest.mark.asyncio
async def test_harness_imports_shared_lib_namespace(tmp_path: Path) -> None:
    task = _scaffold(tmp_path)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    result = await run_harness_package(lock, task, timeout_seconds=20.0, dataset_root=tmp_path)
    env = result["envelope"]
    assert env.get("ok") is True, env
    published = env.get("published") or {}
    assert "session-output" in published
    text = Path(published["session-output"]).read_text(encoding="utf-8")
    assert "from-shared" in text


def test_evaluator_imports_shared_lib_namespace(tmp_path: Path) -> None:
    task = _scaffold(tmp_path)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    art = tmp_path / "session-output.json"
    art.write_text('{"token":"x"}\n', encoding="utf-8")
    raw = run_evaluator_worker(
        task,
        lock,
        {"session-output": str(art)},
        dataset_root=tmp_path,
    )
    assert raw.get("status") == "PASS"
    assert (raw.get("metrics") or {}).get("token") == "from-shared"


def test_evaluator_path_order_task_dir_before_dataset_root(tmp_path: Path) -> None:
    """L0 evaluator inject must match harness: [task_dir, dataset_root]."""
    # Bypass full package lock: only the evaluator worker path inject is under test.
    # Same bare top-level name under both path roots — first on path wins.
    task = tmp_path / "tasks" / "t1"
    task.mkdir(parents=True)
    (task / "order_probe.py").write_text("SOURCE = 'task'\n", encoding="utf-8")
    (tmp_path / "order_probe.py").write_text("SOURCE = 'dataset'\n", encoding="utf-8")
    (task / "evaluator.py").write_text(
        """
import order_probe

def evaluate(payload):
    return {
        "status": "PASS" if order_probe.SOURCE == "task" else "FAIL",
        "score": 1.0 if order_probe.SOURCE == "task" else 0.0,
        "metrics": {"source": order_probe.SOURCE},
    }
""",
        encoding="utf-8",
    )
    art = tmp_path / "session-output.json"
    art.write_text("{}\n", encoding="utf-8")
    raw = run_evaluator_worker(
        task,
        lock=object(),
        artifacts_map={"session-output": str(art)},
        dataset_root=tmp_path,
    )
    assert raw.get("status") == "PASS", raw
    assert (raw.get("metrics") or {}).get("source") == "task"


@pytest.mark.asyncio
async def test_same_basename_shared_and_task_lib_coexist(tmp_path: Path) -> None:
    """shared.lib.bridge_mod and lib.bridge_mod must both resolve (#68)."""
    task = _scaffold(tmp_path, with_task_lib=True)
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    result = await run_harness_package(lock, task, timeout_seconds=20.0, dataset_root=tmp_path)
    env = result["envelope"]
    assert env.get("ok") is True, env
    text = Path((env.get("published") or {})["session-output"]).read_text(encoding="utf-8")
    assert "from-task-lib" in text
    assert "from-shared" in text
    art = tmp_path / "session-output.json"
    art.write_text("{}\n", encoding="utf-8")
    raw = run_evaluator_worker(
        task,
        lock,
        {"session-output": str(art)},
        dataset_root=tmp_path,
    )
    assert raw.get("status") == "PASS", raw
    metrics = raw.get("metrics") or {}
    assert metrics.get("task") == "from-task-lib"
    assert metrics.get("shared") == "from-shared"


def test_evaluator_timeout_returns_error_not_raise(tmp_path: Path) -> None:
    task = tmp_path / "tasks" / "t1"
    task.mkdir(parents=True)
    (task / "evaluator.py").write_text(
        "import time\n"
        "def evaluate(payload):\n"
        "    time.sleep(30)\n"
        "    return {'status': 'PASS', 'score': 1.0, 'metrics': {}}\n",
        encoding="utf-8",
    )
    art = tmp_path / "session-output.json"
    art.write_text("{}\n", encoding="utf-8")
    lock = SimpleNamespace(
        digest="sha256:" + "a" * 64,
        limits=freeze({"wall_time_seconds": 0.3}),
    )
    raw = run_evaluator_worker(
        task,
        lock,
        {"session-output": str(art)},
        dataset_root=tmp_path,
    )
    assert raw.get("status") == "ERROR"
    metrics = raw.get("metrics") or {}
    assert metrics.get("error") == "evaluator_timeout"
    assert metrics.get("timeout_seconds") == 0.3


def test_evaluator_timeout_respects_lock_limits(tmp_path: Path) -> None:
    """Lock wall_time_seconds must drive the supervised timeout (not a hardcoded 60)."""
    task = tmp_path / "tasks" / "t1"
    task.mkdir(parents=True)
    (task / "evaluator.py").write_text(
        "import time\n"
        "def evaluate(payload):\n"
        "    time.sleep(5)\n"
        "    return {'status': 'PASS', 'score': 1.0, 'metrics': {}}\n",
        encoding="utf-8",
    )
    art = tmp_path / "session-output.json"
    art.write_text("{}\n", encoding="utf-8")
    lock = SimpleNamespace(
        digest="sha256:" + "b" * 64,
        limits=freeze({"wall_time_seconds": 0.4}),
    )
    raw = run_evaluator_worker(
        task,
        lock,
        {"session-output": str(art)},
        dataset_root=tmp_path,
    )
    assert raw.get("status") == "ERROR"
    assert (raw.get("metrics") or {}).get("timeout_seconds") == 0.4
