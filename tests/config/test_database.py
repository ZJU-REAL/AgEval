"""Database manifest, list_tasks, resolve_task unit tests (Spec 20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.database import (
    list_tasks,
    load_database_manifest,
    member_paths_for_digest,
    resolve_task,
    validate_database_id,
)
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore

REPO = Path(__file__).resolve().parents[2]
CORE_DB = REPO / "examples" / "core"
JOURNEYS_DB = REPO / "examples" / "journeys"


def _write_db(
    root: Path,
    *,
    database_id: str = "test/suite",
    version: str = "0.1.0",
    defaults: str | None = None,
    extra_root: str = "",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    body = (
        f"format: bora.database/1\n"
        f"database_id: {database_id}\n"
        f'version: "{version}"\n'
        f"tasks:\n  root: tasks\n"
    )
    if defaults:
        body += f"defaults:\n{defaults}"
    body += extra_root
    (root / "bora.yaml").write_text(body, encoding="utf-8")


def _write_task(task_dir: Path, task_id: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        f"""
format: bora.task/1
task_id: {task_id}
harness: {{runtime: python, entrypoint: harness:run}}
parameters: {{}}
provider: {{kind: local, assurance: l0}}
agent_profiles: []
limits: {{wall_time_seconds: 10, agent_invocations: 1, environment_actions: 0}}
artifacts: {{publishable: []}}
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs: []
  output: {{format: json}}
""",
        encoding="utf-8",
    )
    (task_dir / "harness.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (task_dir / "evaluator.py").write_text(
        "def evaluate(i): return {'status':'PASS','score':1}\n", encoding="utf-8"
    )


def test_examples_core_manifest() -> None:
    man = load_database_manifest(CORE_DB)
    assert man.database_id == "example/core"
    assert man.format == "bora.database/1"
    ids = list_tasks(CORE_DB, manifest=man)
    assert "config-minimal" in ids
    assert "sdk-agent-session" in ids
    assert len(ids) >= 10


def test_resolve_and_lock_public_example() -> None:
    resolved = resolve_task(CORE_DB, "config-minimal")
    assert resolved.database_id == "example/core"
    assert resolved.task_dir.name == "config-minimal"
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        resolved.task_dir,
        "config-minimal",
        capabilities=DeclarationCapabilityCatalog(),
    )
    assert lock.task_id == "config-minimal"
    assert lock.digest.startswith("sha256:")


def test_unknown_task(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    with pytest.raises(ConfigError) as ei:
        resolve_task(tmp_path, "missing")
    assert ei.value.error_code == "unknown_task"


def test_empty_database_fail_closed(tmp_path: Path) -> None:
    _write_db(tmp_path)
    (tmp_path / "tasks").mkdir()
    with pytest.raises(ConfigError) as ei:
        list_tasks(tmp_path)
    assert ei.value.error_code == "invalid_package"
    assert "zero tasks" in ei.value.message


def test_directory_task_id_mismatch(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "dir-name", "other-id")
    with pytest.raises(ConfigError) as ei:
        list_tasks(tmp_path)
    assert ei.value.error_code == "unknown_task"


def test_task_schema_at_database_root_rejected(tmp_path: Path) -> None:
    (tmp_path / "bora.yaml").write_text(
        "format: bora.task/1\ntask_id: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        load_database_manifest(tmp_path)
    assert ei.value.error_code == "invalid_format"


def test_illegal_database_id(tmp_path: Path) -> None:
    for bad in ("../escape", "/abs", "HasCaps", "trail/", "//double", ""):
        if not bad:
            continue
        _write_db(tmp_path, database_id=bad)
        with pytest.raises(ConfigError) as ei:
            load_database_manifest(tmp_path)
        assert ei.value.error_code in {"invalid_schema", "invalid_format"}


def test_validate_database_id_charset() -> None:
    validate_database_id("a")
    validate_database_id("example/core")
    validate_database_id("org.name/area_1")
    with pytest.raises(ConfigError):
        validate_database_id("Bad")
    with pytest.raises(ConfigError):
        validate_database_id("a//b")


def test_illegal_defaults_key(tmp_path: Path) -> None:
    _write_db(tmp_path, defaults="  max_concurrent_tasks: 2\n  limits: {}\n")
    with pytest.raises(ConfigError) as ei:
        load_database_manifest(tmp_path)
    assert ei.value.error_code == "invalid_schema"
    assert "defaults" in ei.value.message


def test_forbidden_task_fields_on_database_root(tmp_path: Path) -> None:
    _write_db(tmp_path, extra_root="harness:\n  runtime: python\n")
    with pytest.raises(ConfigError) as ei:
        load_database_manifest(tmp_path)
    assert "harness" in ei.value.message


def test_member_paths_stable_order(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "b", "b")
    _write_task(tmp_path / "tasks" / "a", "a")
    paths = member_paths_for_digest(tmp_path)
    assert paths[0] == "bora.yaml"
    # Members sorted by task id
    a_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/a/"))
    b_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/b/"))
    assert a_idx < b_idx


def test_journeys_list() -> None:
    ids = list_tasks(JOURNEYS_DB)
    assert set(ids) >= {
        "env-postgres-min",
        "multiagent-env-min",
        "tau2-dialog-min",
        "terminal-jsonl-agg",
    }
