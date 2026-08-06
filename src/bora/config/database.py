"""Database (suite) manifest load, member enumeration, and task resolve.

Delivery unit is a Database root with ``bora.yaml`` (``bora.database/1``).
Each member lives under ``tasks/<task_id>/task.yaml`` (``bora.task/1``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from bora.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_UNKNOWN_TASK,
    ConfigError,
)

DATABASE_FORMAT = "bora.database/1"
TASK_CONFIG_FILENAME = "task.yaml"
DEFAULT_TASKS_ROOT = "tasks"

# Constitution D2: database_id charset (case-sensitive; prefer lowercase).
_DATABASE_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$")

# defaults v1 allowlist (suite scheduling only).
_DEFAULTS_ALLOWLIST = frozenset({"max_concurrent_tasks"})

# Task execution keys forbidden on Database root (Constitution D2).
_FORBIDDEN_DATABASE_ROOT_KEYS = frozenset(
    {
        "task_id",
        "harness",
        "parameters",
        "provider",
        "agent_profiles",
        "environment",
        "limits",
        "artifacts",
        "evaluation",
    }
)


@dataclass(frozen=True, slots=True)
class DatabaseDefaults:
    """Optional suite-level defaults consumed only by Application scheduling."""

    max_concurrent_tasks: int | None = None


@dataclass(frozen=True, slots=True)
class DatabaseManifest:
    """Immutable Database root document (``bora.database/1``)."""

    format: str
    database_id: str
    version: str
    tasks_root: str
    description: str | None = None
    defaults: DatabaseDefaults | None = None


@dataclass(frozen=True, slots=True)
class ResolvedTask:
    """Local resolve result: Database root + member task directory."""

    database_root: Path
    task_id: str
    task_dir: Path
    task_config_path: Path
    database_id: str
    database_version: str


def validate_database_id(database_id: str) -> None:
    """Fail closed if *database_id* violates Constitution D2 charset rules."""
    if not isinstance(database_id, str) or not database_id:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id must be a non-empty string",
            location="/database_id",
        )
    if len(database_id) > 128:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id length must be 1–128",
            location="/database_id",
        )
    if ".." in database_id or "//" in database_id:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id must not contain '..' or '//'",
            location="/database_id",
        )
    if database_id.startswith("/") or database_id.endswith("/"):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id must not start or end with '/'",
            location="/database_id",
        )
    if not _DATABASE_ID_RE.fullmatch(database_id):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id charset invalid (expected ^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$)",
            location="/database_id",
        )


def _parse_yaml_mapping(text: str, *, location: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"invalid YAML: {exc}",
            location=location,
        ) from exc
    if data is None:
        raise ConfigError(ERROR_INVALID_SCHEMA, "empty document", location=location)
    if not isinstance(data, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "document root must be a mapping",
            location=location,
        )
    return data


def load_database_manifest(database_root: Path) -> DatabaseManifest:
    """Load and validate Database ``bora.yaml`` from *database_root*."""
    root = database_root.expanduser().resolve(strict=False)
    if not root.is_dir():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"database root is not a directory: {database_root}",
            location=str(database_root),
        )
    path = root / "bora.yaml"
    if not path.is_file():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "bora.yaml not found at database root",
            location="bora.yaml",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"cannot read bora.yaml: {exc}",
            location="bora.yaml",
        ) from exc

    if "${" in text or "os.environ" in text:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "environment variable interpolation is not allowed in bora.yaml",
            location="bora.yaml",
        )

    raw = _parse_yaml_mapping(text, location="bora.yaml")
    return _manifest_from_mapping(raw)


def _manifest_from_mapping(raw: dict[str, Any]) -> DatabaseManifest:
    fmt = raw.get("format")
    if not isinstance(fmt, str) or not fmt:
        raise ConfigError(
            ERROR_INVALID_FORMAT,
            "missing or invalid format",
            location="/format",
        )
    if fmt != DATABASE_FORMAT:
        # Common mistake: pointing CLI at a task member (task schema).
        if fmt == "bora.task/1":
            raise ConfigError(
                ERROR_INVALID_FORMAT,
                "expected bora.database/1 at database root; got bora.task/1 "
                "(pass the Database root, not a task member directory)",
                location="/format",
            )
        raise ConfigError(
            ERROR_INVALID_FORMAT,
            f"unsupported database format: {fmt}",
            location="/format",
        )

    for forbidden in _FORBIDDEN_DATABASE_ROOT_KEYS:
        if forbidden in raw:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"database root must not declare task field {forbidden!r}",
                location=f"/{forbidden}",
            )

    database_id = raw.get("database_id")
    if not isinstance(database_id, str):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "database_id required",
            location="/database_id",
        )
    validate_database_id(database_id)

    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "version must be a non-empty string",
            location="/version",
        )

    tasks_block = raw.get("tasks")
    tasks_root = DEFAULT_TASKS_ROOT
    if tasks_block is not None:
        if not isinstance(tasks_block, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "tasks must be a mapping",
                location="/tasks",
            )
        root_val = tasks_block.get("root", DEFAULT_TASKS_ROOT)
        if not isinstance(root_val, str) or not root_val.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "tasks.root must be a non-empty string",
                location="/tasks/root",
            )
        tasks_root = root_val.strip().replace("\\", "/").strip("/")
        if not tasks_root or ".." in Path(tasks_root).parts or tasks_root.startswith("/"):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "tasks.root must be a relative path without '..'",
                location="/tasks/root",
            )
        unknown_tasks_keys = set(tasks_block) - {"root"}
        if unknown_tasks_keys:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown tasks keys: {sorted(unknown_tasks_keys)}",
                location="/tasks",
            )

    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "description must be a string when set",
            location="/description",
        )

    defaults_obj: DatabaseDefaults | None = None
    defaults_raw = raw.get("defaults")
    if defaults_raw is not None:
        if not isinstance(defaults_raw, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "defaults must be a mapping",
                location="/defaults",
            )
        unknown = set(defaults_raw) - _DEFAULTS_ALLOWLIST
        if unknown:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown defaults keys (v1 allowlist is "
                f"{sorted(_DEFAULTS_ALLOWLIST)}): {sorted(unknown)}",
                location="/defaults",
            )
        mct = defaults_raw.get("max_concurrent_tasks")
        if mct is not None and (not isinstance(mct, int) or isinstance(mct, bool) or mct < 1):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "defaults.max_concurrent_tasks must be an integer ≥ 1",
                location="/defaults/max_concurrent_tasks",
            )
        defaults_obj = DatabaseDefaults(max_concurrent_tasks=mct)

    # Reject unknown top-level keys beyond the wire schema.
    allowed = {"format", "database_id", "version", "tasks", "description", "defaults"}
    unknown_top = set(raw) - allowed
    if unknown_top:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unknown database root keys: {sorted(unknown_top)}",
            location="/",
        )

    return DatabaseManifest(
        format=fmt,
        database_id=database_id,
        version=version.strip(),
        tasks_root=tasks_root,
        description=description,
        defaults=defaults_obj,
    )


def list_tasks(database_root: Path, *, manifest: DatabaseManifest | None = None) -> list[str]:
    """Return sorted task ids under the Database; fail closed on empty or mismatch."""
    root = database_root.expanduser().resolve(strict=False)
    man = manifest or load_database_manifest(root)
    tasks_dir = root / man.tasks_root
    if not tasks_dir.is_dir():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"tasks root not found: {man.tasks_root}",
            location=man.tasks_root,
        )

    ids: list[str] = []
    for entry in sorted(tasks_dir.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        if not entry.is_dir():
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"non-directory entry under tasks root: {entry.name}",
                location=f"{man.tasks_root}/{entry.name}",
            )
        task_yaml = entry / TASK_CONFIG_FILENAME
        if not task_yaml.is_file():
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"missing {TASK_CONFIG_FILENAME} for task {entry.name!r}",
                location=f"{man.tasks_root}/{entry.name}/{TASK_CONFIG_FILENAME}",
            )
        try:
            text = task_yaml.read_text(encoding="utf-8")
            data = _parse_yaml_mapping(
                text,
                location=f"{man.tasks_root}/{entry.name}/{TASK_CONFIG_FILENAME}",
            )
        except ConfigError:
            raise
        except OSError as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot read task config: {exc}",
                location=f"{man.tasks_root}/{entry.name}/{TASK_CONFIG_FILENAME}",
            ) from exc

        fmt = data.get("format")
        if fmt == DATABASE_FORMAT:
            raise ConfigError(
                ERROR_INVALID_FORMAT,
                "task member must use bora.task/1, not bora.database/1",
                location=f"{man.tasks_root}/{entry.name}/{TASK_CONFIG_FILENAME}",
            )
        if fmt != "bora.task/1":
            raise ConfigError(
                ERROR_INVALID_FORMAT,
                f"task member format must be bora.task/1, got {fmt!r}",
                location=f"{man.tasks_root}/{entry.name}/{TASK_CONFIG_FILENAME}",
            )
        yaml_task_id = data.get("task_id")
        if not isinstance(yaml_task_id, str) or not yaml_task_id:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "task.yaml missing task_id",
                location=f"{man.tasks_root}/{entry.name}/task_id",
            )
        if yaml_task_id != entry.name:
            raise ConfigError(
                ERROR_UNKNOWN_TASK,
                f"task_id mismatch: directory={entry.name!r} yaml={yaml_task_id!r}",
                location=f"{man.tasks_root}/{entry.name}/task_id",
            )
        ids.append(entry.name)

    if not ids:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "database has zero tasks (empty suite is not allowed)",
            location=man.tasks_root,
        )
    return ids


def resolve_task(
    database_root: Path,
    task_id: str,
    *,
    manifest: DatabaseManifest | None = None,
) -> ResolvedTask:
    """Resolve *task_id* to a member directory under the Database root."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ConfigError(
            ERROR_UNKNOWN_TASK,
            "task_id must be a non-empty string",
            location="--task",
        )
    task_id = task_id.strip()
    root = database_root.expanduser().resolve(strict=False)
    man = manifest or load_database_manifest(root)
    # Ensure suite is non-empty and members are consistent (also validates all ids).
    known = list_tasks(root, manifest=man)
    if task_id not in known:
        raise ConfigError(
            ERROR_UNKNOWN_TASK,
            f"unknown task_id: {task_id!r} (not a member of this database)",
            location=f"{man.tasks_root}/{task_id}",
        )
    task_dir = (root / man.tasks_root / task_id).resolve(strict=False)
    task_config = task_dir / TASK_CONFIG_FILENAME
    return ResolvedTask(
        database_root=root,
        task_id=task_id,
        task_dir=task_dir,
        task_config_path=task_config,
        database_id=man.database_id,
        database_version=man.version,
    )


def member_paths_for_digest(
    database_root: Path, *, manifest: DatabaseManifest | None = None
) -> list[str]:
    """Stable ordered package-relative paths for suite digest input (Spec 21).

    Returns posix-relative paths under the database root: root ``bora.yaml`` plus
    every file under each member directory, sorted. Does not compute hashes.
    """
    root = database_root.expanduser().resolve(strict=False)
    man = manifest or load_database_manifest(root)
    task_ids = list_tasks(root, manifest=man)
    paths: list[str] = ["bora.yaml"]
    for tid in task_ids:
        task_dir = root / man.tasks_root / tid
        for file_path in sorted(task_dir.rglob("*")):
            if not file_path.is_file():
                continue
            # Skip interpreter caches / most hidden files (Spec 21 may refine).
            if "__pycache__" in file_path.parts or file_path.name.endswith(".pyc"):
                continue
            if file_path.name.startswith(".") and file_path.name not in {".gitignore"}:
                continue
            try:
                rel = file_path.relative_to(root).as_posix()
            except ValueError:
                continue
            paths.append(rel)
    return paths
