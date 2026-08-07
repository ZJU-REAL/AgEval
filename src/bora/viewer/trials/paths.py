"""Path sandboxing and evidence root resolution for viewer trials."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.viewer.jobs import safe_id_segment


def _safe_run_id(run_id: str) -> str:
    return safe_id_segment(run_id, field="run_id")


def _safe_under(root: Path, relative: str) -> Path:
    """Resolve *relative* under *root*; reject traversal and escape."""
    if not relative or relative.startswith(("/", "\\")):
        raise ConfigError(
            "invalid_package",
            "path must be relative",
            location=relative or ".",
        )
    parts = Path(relative).parts
    if ".." in parts:
        raise ConfigError(
            "invalid_package",
            "path traversal rejected",
            location=relative,
        )
    root_resolved = root.resolve(strict=False)
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "path escapes sandbox",
            location=relative,
        ) from exc
    return candidate


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _assert_under_database(root: Path, path: Path, *, location: str) -> Path:
    """Resolve *path* and ensure it stays under Database *root*."""
    root_r = root.resolve(strict=False)
    cand = path.resolve(strict=False)
    try:
        cand.relative_to(root_r)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "path escapes database sandbox",
            location=location,
        ) from exc
    return cand


def _evidence_matches_task(evidence: Path, task_id: str | None) -> bool:
    """If lock.json has task_id, require match; missing lock is ok without require."""
    if not task_id:
        return True
    lock = _read_json_object(evidence / "lock.json")
    if lock is None:
        # No lock: allow only when caller already scoped via suite membership.
        return True
    locked = lock.get("task_id")
    if locked is None:
        return True
    return str(locked) == task_id


def resolve_evidence_root(
    database_root: Path,
    run_id: str,
    *,
    task_id: str | None = None,
    require_task_match: bool = True,
) -> Path:
    """Locate Attempt evidence for *run_id* under the Database root sandbox.

    Lookup order:
    1. ``{database}/.bora/runs/{run_id}``
    2. ``{database}/{tasks_root}/{task_id}/.bora/runs/{run_id}`` when task_id given
    3. Scan ``{database}/tasks/*/.bora/runs/{run_id}`` (bounded)

    When *require_task_match* and *task_id* are set, lock.json ``task_id`` must match
    if present (fail closed on mismatch).
    """
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    tid = safe_id_segment(task_id, field="task_id") if task_id else None

    candidates: list[Path] = []
    primary = root / ".bora" / "runs" / rid
    if primary.is_dir():
        candidates.append(primary)

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    # tasks_root may be multi-segment but must not escape (validated at load).
    if ".." in Path(tasks_root_name).parts or tasks_root_name.startswith(("/", "\\")):
        tasks_root_name = "tasks"

    if tid:
        task_local = root / tasks_root_name / tid / ".bora" / "runs" / rid
        if task_local.is_dir():
            candidates.append(task_local)

    # Bounded scan under tasks/*/.bora/runs (single-segment task ids only)
    tasks_dir = root / tasks_root_name
    if tasks_dir.is_dir():
        for child in tasks_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                safe_id_segment(child.name, field="task_id")
            except ConfigError:
                continue
            cand = child / ".bora" / "runs" / rid
            if cand.is_dir():
                candidates.append(cand)

    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = _assert_under_database(root, cand, location=str(cand))
        except ConfigError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if require_task_match and tid and not _evidence_matches_task(resolved, tid):
            continue
        return resolved

    raise ConfigError(
        "unknown_task",
        f"evidence root not found for run_id={rid!r}" + (f" task_id={tid!r}" if tid else ""),
        location=str(primary),
    )


def parse_query(query: str) -> dict[str, str]:
    """Parse URL query string into first-value map."""
    qs = parse_qs(query or "", keep_blank_values=False)
    return {k: v[0] for k, v in qs.items() if v}
