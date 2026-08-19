"""Local Viewer preview of declared binding.overlays (Dataset files)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ageval.config.errors import ERROR_INVALID_PACKAGE, ERROR_PATH_OUTSIDE_PACKAGE, ConfigError
from ageval.config.overlay_files import (
    iter_overlay_files,
    normalize_overlay_path,
    overlay_paths_from_job_overlay,
    parse_overlay_paths,
    resolve_overlay_target,
)


def declared_overlay_paths(
    dataset_root: Path,
    overlay: Mapping[str, Any] | None,
) -> list[str]:
    """Prefer the job's job_overlay list; else Dataset-root profiles.yaml."""
    listed = overlay_paths_from_job_overlay(overlay)
    if listed:
        return listed
    path = dataset_root.expanduser().resolve(strict=False) / "profiles.yaml"
    if not path.is_file():
        return []
    from ageval.config.profiles import load_job_document

    job = load_job_document(path)
    raw: list[str] = []
    for row in job.profiles.values():
        if not isinstance(row, Mapping):
            continue
        items = row.get("overlays")
        if isinstance(items, list):
            raw.extend(str(item).strip() for item in items if str(item).strip())
    if not raw:
        return []
    return parse_overlay_paths(raw, location="profiles.yaml:/overlays")


def list_overlay_files(dataset_root: Path, prefixes: Sequence[str]) -> dict[str, Any]:
    root = dataset_root.expanduser().resolve(strict=False)
    paths = parse_overlay_paths(list(prefixes), location="/overlays")
    files = iter_overlay_files(root, paths, location="/overlays") if paths else []
    items = [
        {
            "path": item.relative_to(root).as_posix(),
            "name": item.name,
            "type": "file",
            "size": item.stat().st_size,
        }
        for item in files
    ]
    return {"ok": True, "items": items, "prefixes": paths}


def read_overlay_file(
    dataset_root: Path,
    relpath: str,
    prefixes: Sequence[str],
) -> dict[str, Any]:
    root = dataset_root.expanduser().resolve(strict=False)
    allowed = parse_overlay_paths(list(prefixes), location="/overlays")
    path = normalize_overlay_path(relpath, location="/overlays")
    if not any(path == prefix or path.startswith(f"{prefix}/") for prefix in allowed):
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            "path is not in the declared overlays set",
            location=path,
        )
    target = resolve_overlay_target(root, path, location="/overlays")
    if not target.is_file():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"overlay path is not a file: {path}",
            location=path,
        )
    data = target.read_bytes()
    try:
        text = data.decode("utf-8")
        encoding = "utf-8"
        content = text
    except UnicodeDecodeError:
        encoding = "latin-1"
        content = data.decode("latin-1", errors="replace")
    return {
        "ok": True,
        "path": path,
        "size": len(data),
        "encoding": encoding,
        "content": content,
    }
