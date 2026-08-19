"""Dataset manifest, list_tasks, resolve_task unit tests (Spec 20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.dataset import (
    list_tasks,
    load_dataset_manifest,
    member_paths_for_digest,
    resolve_task,
    validate_dataset_id,
)
from ageval.config.errors import ConfigError
from ageval.config.load_and_lock import ConfigCore
from ageval.config.package_fs import LocalPackageReader

REPO = Path(__file__).resolve().parents[2]
CORE_DB = REPO / "examples" / "core"
JOURNEYS_DB = REPO / "examples" / "journeys"


def _write_db(
    root: Path,
    *,
    dataset_id: str = "test/suite",
    version: str = "0.1.0",
    defaults: str | None = None,
    extra_root: str = "",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    body = (
        f"format: ageval.dataset/1\n"
        f"dataset_id: {dataset_id}\n"
        f'version: "{version}"\n'
        f"tasks:\n  root: tasks\n"
    )
    if defaults:
        body += f"defaults:\n{defaults}"
    body += extra_root
    (root / "ageval.yaml").write_text(body, encoding="utf-8")


def _write_task(task_dir: Path, task_id: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        f"""
format: ageval.task/1
task_id: {task_id}
harness: {{runtime: python, entrypoint: harness:run}}
parameters: {{}}
provider: {{kind: local, assurance: l0}}
agent_profiles: []
limits: {{wall_time_seconds: 10, agent_invocations: 1, environment_actions: 0}}
artifacts: {{publishable: []}}
evaluation:
  entrypoint: evaluator:evaluate
  inputs: []
  output: {{format: json}}
""",
        encoding="utf-8",
    )
    (task_dir / "run.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (task_dir / "evaluator.py").write_text(
        "def evaluate(i): return {'status':'PASS','score':1}\n", encoding="utf-8"
    )


def test_examples_core_manifest() -> None:
    man = load_dataset_manifest(CORE_DB)
    assert man.dataset_id == "example/core"
    assert man.format == "ageval.dataset/1"
    ids = list_tasks(CORE_DB, manifest=man)
    assert "config-minimal" in ids
    assert "sdk-agent-session" in ids
    assert len(ids) >= 10


def test_resolve_and_lock_public_example() -> None:
    from ageval.config.profiles import resolve_job_document

    resolved = resolve_task(CORE_DB, "config-minimal")
    assert resolved.dataset_id == "example/core"
    assert resolved.task_dir.name == "config-minimal"
    bindings = resolve_job_document(CORE_DB)
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        resolved.task_dir,
        "config-minimal",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=bindings,
    )
    assert lock.task_id == "config-minimal"
    assert lock.digest.startswith("sha256:")
    assert lock.job_overlay is not None


def test_unknown_task(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    with pytest.raises(ConfigError) as ei:
        resolve_task(tmp_path, "missing")
    assert ei.value.error_code == "unknown_task"


def test_empty_dataset_fail_closed(tmp_path: Path) -> None:
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


def test_task_schema_at_dataset_root_rejected(tmp_path: Path) -> None:
    (tmp_path / "ageval.yaml").write_text(
        "format: ageval.task/1\ntask_id: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        load_dataset_manifest(tmp_path)
    assert ei.value.error_code == "invalid_format"


def test_illegal_dataset_id(tmp_path: Path) -> None:
    for bad in ("../escape", "/abs", "HasCaps", "trail/", "//double", ""):
        if not bad:
            continue
        _write_db(tmp_path, dataset_id=bad)
        with pytest.raises(ConfigError) as ei:
            load_dataset_manifest(tmp_path)
        assert ei.value.error_code in {"invalid_schema", "invalid_format"}


def test_validate_dataset_id_charset() -> None:
    validate_dataset_id("a")
    validate_dataset_id("example/core")
    validate_dataset_id("org.name/area_1")
    with pytest.raises(ConfigError):
        validate_dataset_id("Bad")
    with pytest.raises(ConfigError):
        validate_dataset_id("a//b")


def test_illegal_defaults_key(tmp_path: Path) -> None:
    _write_db(tmp_path, defaults="  max_concurrent_tasks: 2\n  limits: {}\n")
    with pytest.raises(ConfigError) as ei:
        load_dataset_manifest(tmp_path)
    assert ei.value.error_code == "invalid_schema"
    assert "defaults" in ei.value.message


def test_forbidden_task_fields_on_dataset_root(tmp_path: Path) -> None:
    _write_db(tmp_path, extra_root="harness:\n  runtime: python\n")
    with pytest.raises(ConfigError) as ei:
        load_dataset_manifest(tmp_path)
    assert "harness" in ei.value.message


def test_member_paths_stable_order(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "b", "b")
    _write_task(tmp_path / "tasks" / "a", "a")
    paths = member_paths_for_digest(tmp_path)
    assert paths[0] == "ageval.yaml"
    # Members sorted by task id
    a_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/a/"))
    b_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/b/"))
    assert a_idx < b_idx


def test_member_paths_include_shared_tree(tmp_path: Path) -> None:
    """#65: optional shared/** enters packageDigest input paths."""
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    shared_lib = tmp_path / "shared" / "lib"
    shared_lib.mkdir(parents=True)
    (shared_lib / "bridge.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "shared" / "assets").mkdir()
    (tmp_path / "shared" / "assets" / "policy.json").write_text("{}", encoding="utf-8")
    # Hidden / pycache must stay out
    (shared_lib / "__pycache__").mkdir()
    (shared_lib / "__pycache__" / "bridge.cpython-312.pyc").write_bytes(b"x")
    (tmp_path / "shared" / ".env").write_text("SECRET=1\n", encoding="utf-8")

    paths = member_paths_for_digest(tmp_path)
    assert "shared/lib/bridge.py" in paths
    assert "shared/assets/policy.json" in paths
    assert not any("__pycache__" in p for p in paths)
    assert "shared/.env" not in paths
    # shared before tasks (sorted path walk of shared, then tasks by id)
    shared_idx = paths.index("shared/assets/policy.json")
    task_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/a/"))
    assert shared_idx < task_idx


def test_member_paths_include_only_declared_overlays(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    skill = tmp_path / "overlays" / "skills" / "jsonl-agg"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (tmp_path / "overlays" / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (tmp_path / "overlays" / "secret.json").write_text("{}\n", encoding="utf-8")
    alt = tmp_path / "acp-profiles"
    alt.mkdir()
    (alt / "profiles.acp.demo.yaml").write_text(
        "format: ageval.profiles/1\n"
        "bindings:\n"
        "  solver:\n"
        "    executor: openai-http\n"
        "    overlays:\n"
        "      - overlays/skills/jsonl-agg\n"
        "      - overlays/AGENTS.md\n",
        encoding="utf-8",
    )

    paths = member_paths_for_digest(tmp_path)
    assert "acp-profiles/profiles.acp.demo.yaml" in paths
    assert "overlays/AGENTS.md" in paths
    assert "overlays/skills/jsonl-agg/SKILL.md" in paths
    assert "overlays/secret.json" not in paths
    overlay_idx = paths.index("overlays/AGENTS.md")
    task_idx = next(i for i, p in enumerate(paths) if p.startswith("tasks/a/"))
    assert overlay_idx < task_idx


def test_member_paths_omit_undeclared_overlays(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    (tmp_path / "overlays").mkdir()
    (tmp_path / "overlays" / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    paths = member_paths_for_digest(tmp_path)
    assert not any(p.startswith("overlays/") for p in paths)


def test_member_paths_without_shared_unchanged_shape(tmp_path: Path) -> None:
    _write_db(tmp_path)
    _write_task(tmp_path / "tasks" / "a", "a")
    paths = member_paths_for_digest(tmp_path)
    assert not any(p.startswith("shared/") for p in paths)
    assert paths[0] == "ageval.yaml"


def test_journeys_list() -> None:
    ids = list_tasks(JOURNEYS_DB)
    assert set(ids) >= {
        "env-postgres-min",
        "multiagent-env-min",
        "tau2-dialog-min",
        "terminal-jsonl-agg",
    }
