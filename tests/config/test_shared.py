"""Dataset-level shared/ validation and reserved-name rules (#65 layout, #68 namespaces)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.helpers.lock import lock_with_profiles

from ageval.config.errors import ConfigError
from ageval.config.shared import (
    find_lib_collisions,
    find_task_shared_shadows,
    top_level_import_names,
    validate_shared_layout,
)

ACP_SOLVER = {
    "solver": {
        "executor": "acp",
        "options": {"entry": "codex"},
        "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
    }
}


def _write_db(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ageval.yaml").write_text(
        "format: ageval.dataset/1\n"
        "dataset_id: test/shared-suite\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )


def _write_task(task_dir: Path, task_id: str, *, lib_mod: str | None = None) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        f"""format: ageval.task/1
task_id: {task_id}
agent_profiles: []
limits:
  wall_time_seconds: 60
  agent_invocations: 0
artifacts:
  publishable: []
evaluation:
  entrypoint: evaluator:evaluate
  inputs: []
""",
        encoding="utf-8",
    )
    (task_dir / "run.py").write_text(
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


def test_same_stem_across_shared_and_task_lib_allowed(tmp_path: Path) -> None:
    """#68: shared.lib.bridge vs lib.bridge — same basename is fine."""
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("x=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "a", "a", lib_mod="bridge")
    assert find_lib_collisions(tmp_path) == []
    validate_shared_layout(tmp_path)  # no raise


def test_task_shared_dir_forbidden(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    (tmp_path / "tasks" / "a" / "shared").mkdir()
    hits = find_task_shared_shadows(tmp_path)
    assert hits == ["tasks/a/shared"]
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path)
    assert "shared" in ei.value.message
    assert ei.value.error_code == "invalid_package"


def test_task_shared_py_forbidden(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    (tmp_path / "tasks" / "a" / "shared.py").write_text("x=1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path)
    assert "shared" in ei.value.message


def test_forbidden_env_under_shared(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    (tmp_path / "shared" / "lib").mkdir(parents=True)
    (tmp_path / "shared" / ".env").write_text("K=v\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path)
    assert ".env" in ei.value.message


def test_lock_fails_on_task_shared_shadow(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "common.py").write_text("V=1\n", encoding="utf-8")
    task = tmp_path / "tasks" / "t1"
    _write_task(task, "t1")
    (task / "shared").mkdir()
    with pytest.raises(ConfigError) as ei:
        lock_with_profiles(
            task,
            "t1",
            {
                "solver": {
                    "executor": "acp",
                    "options": {"entry": "codex"},
                    "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
                }
            },
        )
    assert "shared" in ei.value.message


def test_lock_ok_with_same_stem(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("V=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "t1", "t1", lib_mod="bridge")
    lock = lock_with_profiles(
        tmp_path / "tasks" / "t1",
        "t1",
        {
            "solver": {
                "executor": "acp",
                "options": {"entry": "codex"},
                "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
            }
        },
    )
    assert lock.digest.startswith("sha256:")


def test_lock_ok_with_shared_no_shadow(tmp_path: Path) -> None:
    _write_db(tmp_path)
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("V=1\n", encoding="utf-8")
    _write_task(tmp_path / "tasks" / "t1", "t1", lib_mod="task_only")
    lock = lock_with_profiles(
        tmp_path / "tasks" / "t1",
        "t1",
        {
            "solver": {
                "executor": "acp",
                "options": {"entry": "codex"},
                "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
            }
        },
    )
    assert lock.digest.startswith("sha256:")


def test_infer_walks_up_for_nested_tasks_root(tmp_path: Path) -> None:
    """Shadow gate must fire even when tasks.root is nested (not just tasks/)."""
    from ageval.config.shared import infer_dataset_root_from_task

    (tmp_path / "ageval.yaml").write_text(
        "format: ageval.dataset/1\n"
        "dataset_id: test/nested\n"
        'version: "0.1.0"\n'
        "tasks:\n  root: members/group\n",
        encoding="utf-8",
    )
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("x=1\n", encoding="utf-8")
    task = tmp_path / "members" / "group" / "t1"
    _write_task(task, "t1", lib_mod="bridge")
    (task / "shared.py").write_text("bad=1\n", encoding="utf-8")
    assert infer_dataset_root_from_task(task) == tmp_path.resolve()
    with pytest.raises(ConfigError) as ei:
        validate_shared_layout(tmp_path, tasks_root="members/group")
    assert "shared" in ei.value.message
    with pytest.raises(ConfigError) as ei2:
        lock_with_profiles(
            task,
            "t1",
            {
                "solver": {
                    "executor": "acp",
                    "options": {"entry": "codex"},
                    "extensions": [{"plugin": "acp"}, {"plugin": "local"}],
                }
            },
        )
    assert "shared" in ei2.value.message
