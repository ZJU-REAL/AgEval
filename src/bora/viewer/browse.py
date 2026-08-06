"""Safe filesystem browse helpers for a local Database root.

All file access is confined under the opened Database directory.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from bora.config.database import (
    list_tasks,
    load_database_manifest,
    resolve_task,
)
from bora.config.errors import ConfigError
from bora.registry.resolve import resolve_database_root

# Hard caps for preview payloads (viewer is local-only, still stay bounded).
MAX_TEXT_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_TREE_ENTRIES = 2_000

_TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".py",
        ".yaml",
        ".yml",
        ".json",
        ".jsonl",
        ".toml",
        ".ini",
        ".cfg",
        ".sh",
        ".bash",
        ".zsh",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".css",
        ".html",
        ".htm",
        ".xml",
        ".csv",
        ".tsv",
        ".rs",
        ".go",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".rb",
        ".php",
        ".sql",
        ".r",
        ".dockerfile",
        ".gitignore",
        ".env.example",
    }
)

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"})

# Prefer these names for README / instruction tabs.
_README_CANDIDATES = (
    "README.md",
    "README.zh-CN.md",
    "readme.md",
    "README.txt",
    "README",
)
_INSTRUCTION_CANDIDATES = (
    "instruction.md",
    "INSTRUCTION.md",
    "data/instruction.md",
    "prompt.md",
    "task.md",
)


def open_database(database_ref: str | Path) -> Path:
    """Resolve and validate a Database root for viewing."""
    return resolve_database_root(database_ref)


def database_overview(root: Path) -> dict[str, Any]:
    man = load_database_manifest(root)
    task_ids = list_tasks(root, manifest=man)
    return {
        "database_id": man.database_id,
        "version": man.version,
        "description": man.description,
        "tasks_root": man.tasks_root,
        "task_ids": task_ids,
        "task_count": len(task_ids),
        "root": str(root),
    }


def commands_for(root: Path, *, task_id: str | None = None) -> dict[str, str]:
    """Copyable CLI strings matching current public surface."""
    # Prefer relative path when under cwd for nicer copy-paste.
    try:
        display = str(root.relative_to(Path.cwd()))
    except ValueError:
        display = str(root)

    cmds: dict[str, str] = {
        "tasks": f"bora tasks {display}",
        "run_suite": f"bora run {display}",
        "lock_suite_hint": f"bora lock {display} --task <task_id>",
    }
    if task_id:
        cmds["run_task"] = f"bora run {display} --task {task_id}"
        cmds["lock_task"] = f"bora lock {display} --task {task_id}"
    return cmds


def _safe_join(base: Path, rel: str) -> Path:
    """Join *rel* under *base*; raise ConfigError on escape."""
    if rel is None:
        raise ConfigError("invalid_package", "path required", location="path")
    text = str(rel).replace("\\", "/").lstrip("/")
    if text in {"", "."}:
        target = base.resolve(strict=False)
    else:
        if ".." in Path(text).parts:
            raise ConfigError(
                "invalid_package",
                "path must not contain '..'",
                location=text,
            )
        target = (base / text).resolve(strict=False)
    base_resolved = base.resolve(strict=False)
    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "path escapes database root",
            location=text,
        ) from exc
    return target


def _read_text_if_small(path: Path, *, limit: int = MAX_TEXT_BYTES) -> str | None:
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > limit:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    # Reject if null bytes dominate (binary)
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None


def _find_first(task_dir: Path, names: tuple[str, ...]) -> tuple[str, str] | None:
    for name in names:
        path = task_dir / name
        if path.is_file():
            text = _read_text_if_small(path)
            if text is not None:
                return name, text
    return None


def task_detail(root: Path, task_id: str) -> dict[str, Any]:
    resolved = resolve_task(root, task_id)
    task_dir = resolved.task_dir
    readme = _find_first(task_dir, _README_CANDIDATES)
    instruction = _find_first(task_dir, _INSTRUCTION_CANDIDATES)

    task_yaml_text = _read_text_if_small(resolved.task_config_path)

    return {
        "task_id": task_id,
        "task_dir": str(task_dir.relative_to(root)),
        "readme": {"path": readme[0], "content": readme[1]} if readme else None,
        "instruction": (
            {"path": instruction[0], "content": instruction[1]} if instruction else None
        ),
        "task_yaml": task_yaml_text,
        "commands": commands_for(root, task_id=task_id),
    }


def _should_skip_name(name: str) -> bool:
    if name in {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"}:
        return True
    return name.endswith(".pyc")


def file_tree(root: Path, task_id: str) -> dict[str, Any]:
    """Build a nested tree of the task directory (not the whole Database)."""
    resolved = resolve_task(root, task_id)
    task_dir = resolved.task_dir
    entries = 0

    def walk(dir_path: Path, rel: str) -> dict[str, Any]:
        nonlocal entries
        children: list[dict[str, Any]] = []
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            return {
                "name": dir_path.name,
                "path": rel,
                "type": "dir",
                "error": str(exc),
                "children": [],
            }
        for item in items:
            if _should_skip_name(item.name):
                continue
            entries += 1
            if entries > MAX_TREE_ENTRIES:
                children.append(
                    {
                        "name": "…",
                        "path": rel,
                        "type": "truncated",
                        "message": f"tree truncated at {MAX_TREE_ENTRIES} entries",
                    }
                )
                break
            child_rel = f"{rel}/{item.name}" if rel else item.name
            if item.is_dir():
                children.append(walk(item, child_rel))
            else:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
                children.append(
                    {
                        "name": item.name,
                        "path": child_rel,
                        "type": "file",
                        "size": size,
                    }
                )
        return {
            "name": dir_path.name if rel else task_id,
            "path": rel or ".",
            "type": "dir",
            "children": children,
        }

    return {
        "task_id": task_id,
        "root": task_id,
        "tree": walk(task_dir, ""),
        "entry_count": entries,
    }


def classify_file(path: Path) -> str:
    ext = path.suffix.lower()
    name = path.name.lower()
    if name in {"dockerfile", "makefile"} or ext in _TEXT_EXTENSIONS:
        return "text"
    if ext in _IMAGE_EXTENSIONS:
        return "image"
    # Heuristic: no extension small files often text
    if not ext:
        return "text"
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("text/"):
        return "text"
    if mime and mime.startswith("image/"):
        return "image"
    return "binary"


def read_task_file(root: Path, task_id: str, rel_path: str) -> dict[str, Any]:
    """Read a single file under the task directory for preview."""
    resolved = resolve_task(root, task_id)
    target = _safe_join(resolved.task_dir, rel_path)
    if not target.is_file():
        raise ConfigError(
            "invalid_package",
            f"file not found: {rel_path}",
            location=rel_path,
        )
    kind = classify_file(target)
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise ConfigError("invalid_package", str(exc), location=rel_path) from exc

    result: dict[str, Any] = {
        "task_id": task_id,
        "path": rel_path.replace("\\", "/"),
        "name": target.name,
        "size": size,
        "kind": kind,
        "language": _language_for(target),
    }

    if kind == "text":
        if size > MAX_TEXT_BYTES:
            result["content"] = None
            result["truncated"] = True
            result["message"] = f"file larger than {MAX_TEXT_BYTES} bytes; open on disk"
        else:
            text = _read_text_if_small(target, limit=MAX_TEXT_BYTES)
            if text is None:
                result["kind"] = "binary"
                result["content"] = None
                result["message"] = "could not decode as UTF-8 text"
            else:
                result["content"] = text
                result["truncated"] = False
    elif kind == "image":
        if size > MAX_IMAGE_BYTES:
            result["content_base64"] = None
            result["truncated"] = True
            result["message"] = f"image larger than {MAX_IMAGE_BYTES} bytes"
        else:
            import base64

            data = target.read_bytes()
            mime, _ = mimetypes.guess_type(str(target))
            result["mime"] = mime or "application/octet-stream"
            result["content_base64"] = base64.b64encode(data).decode("ascii")
            result["truncated"] = False
    else:
        result["content"] = None
        result["message"] = "binary file; preview not available"

    return result


def _language_for(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".py": "python",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".jsonl": "json",
        ".md": "markdown",
        ".markdown": "markdown",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".css": "css",
        ".html": "html",
        ".sh": "bash",
        ".toml": "toml",
        ".rs": "rust",
        ".go": "go",
        ".sql": "sql",
    }
    if path.name.lower() == "dockerfile":
        return "dockerfile"
    return mapping.get(ext, "text")
