"""Dataset-level shared/ validation and collision rules (#65)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.shared import (
    find_lib_collisions,
    top_level_import_names,
    validate_shared_layout,
)


def _write_db(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bora.yaml").write_text(
        "format: bora.database/1\n"
        "database_id: test/shared-suite\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )


def _write_task(task_dir: Path, task_id: str, *, lib_mod: str | None = None) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        f"""format: bora.task/1
task_id: {task_id}
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
  publishable: []
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs: []
  output:
    format: json
""",
        encoding="utf-8",
    )
    (task_dir / "harness.py").write_text(
        "def run(ctx):\n    return None\n",
        encoding="utf-8",
    )
    (task_dir / "evaluator.py").write_text(
        "def evaluate(payload):\n    return {'status': 'PASS', 'score': 1.0, 'metrics': {}}\n",
        encoding="utf-8",
    )
    if lib_mod:
        lib = task_dir / "lib"
        lib.mkdir(exist_ok=True)
        (lib / f"{lib_mod}.py").write_text(f"NAME = {lib_mod!r}\n", encoding="utf-8")


def test_top_level_import_names(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "bridge.py").write_text("x=1\n", encoding="utf-8")
    (lib / "pkg").mkdir()
    (lib / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (lib / "__pycache__").mkdir()
    assert top_level_import_names(lib) == {"bridge", "pkg"}


def test_no_shared_is_noop(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    validate_shared_layout(tmp_path)  # no raise


def test_collision_ban(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("x=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "a", "a", lib_mod="bridge")
    hits = find_lib_collisions(tmp_path)
    assert hits == [("bridge", "shared/lib", "tasks/a/lib")]
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path)
    assert "collision" in ei.value.message
    assert ei.value.error_code == "invalid_package"


def test_forbidden_env_under_shared(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    (tmp_path / "shared" / "lib").mkdir(parents=True)
    (tmp_path / "shared" / ".env").write_text("K=v\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path)
    assert ".env" in ei.value.message


def test_lock_fails_on_lib_collision(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "common.py").write_text("V=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "t1", "t1", lib_mod="common")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(
            tmp_path / "tasks" / "t1",
            "t1",
            capabilities=DeclarationCapabilityCatalog(),
        )
    assert "collision" in ei.value.message


def test_lock_ok_with_shared_no_collision(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("V=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "t1", "t1", lib_mod="task_only")
    core = ConfigCore(package_reader=LocalPackageReader())
    lock = core.load_and_lock(
        tmp_path / "tasks" / "t1",
        "t1",
        capabilities=DeclarationCapabilityCatalog(),
    )
    assert lock.digest.startswith("sha256:")


def test_infer_walks_up_for_nested_tasks_root(tmp_path: Path) -> None:
    """Collision gate must fire even when tasks.root is nested (not just tasks/)."""
    from bora.config.shared import infer_database_root_from_task

    (tmp_path / "bora.yaml").write_text(
        "format: bora.database/1\n"
        "database_id: test/nested\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: members/group\n",
        encoding="utf-8",
    )
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("x=1\n", encoding="utf-8")
    task = tmp_path / "members" / "group" / "t1"
    _write_task(task, "t1", lib_mod="bridge")
    assert infer_database_root_from_task(task) == tmp_path.resolve()
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path, tasks_root="members/group")
    assert "collision" in ei.value.message
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei2:
        core.load_and_lock(task, "t1", capabilities=DeclarationCapabilityCatalog())
    assert "collision" in ei2.value.message
