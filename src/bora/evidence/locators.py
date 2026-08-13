"""Portable evidence locators for sealed Attempt / campaign products (#70).

Sealed JSON must never embed host absolute paths (home dirs, /var/folders, …).
Canonical form (option A): ``.bora/runs/<run_id>`` relative to the Database root.

Readers should accept this form, bare ``run_id`` directory names, and legacy
absolute paths (via ``extract_run_id``-style parsing).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def default_runs_root(database_root: Path | str) -> Path:
    """Database-root Attempt evidence directory: ``<db>/.bora/runs``."""
    return Path(database_root) / ".bora" / "runs"


def portable_run_locator(
    run_dir: Path | str,
    *,
    database_root: Path | str | None = None,
) -> str:
    """Return a portable locator for an Attempt evidence directory.

    Preference order:
    1. Relative path under *database_root* (typically ``.bora/runs/<run_id>``).
    2. Suffix ``.bora/runs/<run_id>`` extracted from an absolute path.
    3. Bare directory name (last path component) when it looks like a run id.
    4. As a last resort, the string form of *run_dir* only if it is already
       relative and does not start with a host root — never expanduser homes.
    """
    path = Path(run_dir)
    db = Path(database_root).expanduser().resolve(strict=False) if database_root else None

    if db is not None:
        try:
            abs_run = path if path.is_absolute() else (db / path)
            abs_run = abs_run.resolve(strict=False)
            rel = abs_run.relative_to(db)
            # Normalize to posix-style for cross-machine sealed JSON
            text = rel.as_posix()
            if text and not text.startswith(".."):
                return text
        except (ValueError, OSError):
            pass

    parts = path.parts
    if ".bora" in parts and "runs" in parts:
        try:
            i = parts.index(".bora")
            if i + 2 < len(parts) and parts[i + 1] == "runs":
                return "/".join(parts[i : i + 3])
        except ValueError:
            pass
        # longer: .bora/runs/<id>/...
        try:
            i = list(parts).index("runs")
            if i > 0 and parts[i - 1] == ".bora" and i + 1 < len(parts):
                return f".bora/runs/{parts[i + 1]}"
        except ValueError:
            pass

    name = path.name
    if name and name not in {".", ".."} and not _looks_like_host_root(path):
        # Prefer .bora/runs/<name> when name looks like a run directory.
        if name.startswith("sha256_") or "_run_" in name or name.startswith("run_"):
            return f".bora/runs/{name}"
        if not path.is_absolute():
            return path.as_posix()
        return name

    # Absolute path with no recoverable relative form — still avoid full host path:
    return name or "run"


def _looks_like_host_root(path: Path) -> bool:
    """True if *path* is clearly a host absolute root we must not seal as-is."""
    if not path.is_absolute():
        return False
    s = str(path)
    if s.startswith("/Users/") or s.startswith("/home/") or s.startswith("/var/folders/"):
        return True
    if len(s) >= 3 and s[1] == ":" and s[0].isalpha():  # Windows drive
        return True
    if s.startswith("/tmp/") or s.startswith("/private/var/"):
        return True
    return path.is_absolute()


def resolve_evidence_root(
    database_root: Path | str,
    run_id: str,
    *,
    task_id: str | None = None,
    require_task_match: bool = True,
) -> Path:
    """Locate Attempt evidence for *run_id* under the Database root sandbox.

    Lookup order mirrors the former viewer helper:
    1. ``{database}/.bora/runs/{run_id}``
    2. ``{database}/{tasks_root}/{task_id}/.bora/runs/{run_id}`` when task_id given
    3. Bounded scan under ``tasks/*/.bora/runs/{run_id}``

    Raises ``ConfigError`` when no candidate is found (or task_id mismatches).
    """
    import contextlib
    import json

    from bora.config.database import load_database_manifest
    from bora.config.errors import ConfigError

    def _safe_segment(value: str, *, field: str) -> str:
        text = str(value or "").strip()
        if not text or "/" in text or "\\" in text or text in {".", ".."}:
            raise ConfigError("invalid_package", f"invalid {field}", location=text or ".")
        return text

    def _under(root: Path, path: Path, *, location: str) -> Path:
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

    def _matches_task(evidence: Path, tid: str | None) -> bool:
        if not tid:
            return True
        lock_path = evidence / "lock.json"
        if not lock_path.is_file():
            return True
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return True
        if not isinstance(lock, dict):
            return True
        locked = lock.get("task_id")
        if locked is None:
            return True
        return str(locked) == tid

    root = Path(database_root).expanduser().resolve(strict=False)
    rid = _safe_segment(run_id, field="run_id")
    tid = _safe_segment(task_id, field="task_id") if task_id else None

    candidates: list[Path] = []
    primary = root / ".bora" / "runs" / rid
    if primary.is_dir():
        candidates.append(primary)

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    if ".." in Path(tasks_root_name).parts or tasks_root_name.startswith(("/", "\\")):
        tasks_root_name = "tasks"

    if tid:
        task_local = root / tasks_root_name / tid / ".bora" / "runs" / rid
        if task_local.is_dir():
            candidates.append(task_local)

    tasks_dir = root / tasks_root_name
    if tasks_dir.is_dir():
        for child in tasks_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                _safe_segment(child.name, field="task_id")
            except ConfigError:
                continue
            cand = child / ".bora" / "runs" / rid
            if cand.is_dir():
                candidates.append(cand)

    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = _under(root, cand, location=str(cand))
        except ConfigError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if require_task_match and tid and not _matches_task(resolved, tid):
            continue
        return resolved

    raise ConfigError(
        "unknown_task",
        f"evidence root not found for run_id={rid!r}" + (f" task_id={tid!r}" if tid else ""),
        location=str(primary),
    )


def resolve_attempt_run_dir(database_root: Path | str, run_id: str) -> Path:
    """Resolve ``.bora/runs/<run_id>`` under the Database root; fail closed."""
    from bora.config.errors import ConfigError

    text = (run_id or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text or ".." in text:
        raise ConfigError(
            "invalid_package",
            f"invalid run_id: {run_id!r}",
            location="run_id",
        )
    root = Path(database_root).expanduser().resolve(strict=False)
    runs_root = (root / ".bora" / "runs").resolve(strict=False)
    candidate = (runs_root / text).resolve(strict=False)
    try:
        candidate.relative_to(runs_root)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            f"invalid run_id path: {run_id!r}",
            location="run_id",
        ) from exc
    if candidate.is_dir():
        return candidate
    raise ConfigError(
        "invalid_package",
        f"run directory not found: {candidate}",
        location=str(candidate),
    )


def resolve_run_dir(
    database_root: Path | str,
    locator: Path | str | None,
) -> Path | None:
    """Resolve a portable (or legacy absolute) locator to an on-disk run directory.

    Returns ``None`` when *locator* is empty or cannot be resolved under the
    Database root (legacy abs outside the root still returns the abs Path if it
    exists — operator recovery).
    """
    if locator is None:
        return None
    text = str(locator).strip()
    if not text:
        return None
    root = Path(database_root).expanduser().resolve(strict=False)
    path = Path(text)

    if path.is_absolute():
        resolved = path.expanduser().resolve(strict=False)
        if resolved.is_dir():
            return resolved
        # Fall through: maybe abs path is dead but portable form can be derived
        portable = portable_run_locator(path, database_root=root)
        cand = root / portable
        if cand.is_dir():
            return cand
        return resolved if resolved.exists() else None

    # Relative / portable
    cand = (root / path).resolve(strict=False)
    if cand.is_dir():
        return cand
    # Bare run_id
    bare = root / ".bora" / "runs" / path.name
    if bare.is_dir():
        return bare
    return cand if cand.exists() else None


def portable_artifact_ref(
    path: Path | str,
    *,
    run_dir: Path | str | None = None,
    hold_dir: Path | str | None = None,
) -> str:
    """Portable form for a published artifact path under the Attempt hold/run.

    Prefer path relative to *run_dir* or *hold_dir*; otherwise basename only.
    Never seals host temp roots (``/var/folders``, ``/tmp/bora-artifacts-…``).
    """
    p = Path(path)
    for base in (run_dir, hold_dir):
        if base is None:
            continue
        base_p = Path(base)
        try:
            abs_p = p if p.is_absolute() else (base_p / p)
            abs_p = abs_p.resolve(strict=False)
            abs_base = base_p.resolve(strict=False)
            rel = abs_p.relative_to(abs_base)
            text = rel.as_posix()
            if text and not text.startswith(".."):
                return text
        except (ValueError, OSError):
            continue
    return p.name


def seal_harness_for_evidence(
    harness_out: dict[str, Any],
    *,
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Copy harness_out for sealed harness.json without host temp absolute paths.

    Runtime evaluation still uses the original in-memory absolute hold paths.
    """
    import copy

    doc = copy.deepcopy(harness_out)
    hold_raw = doc.get("artifact_hold")
    hold_path = Path(str(hold_raw)) if hold_raw else None
    # Omit absolute hold; record only that a hold existed (boolean).
    if "artifact_hold" in doc:
        doc["artifact_hold"] = bool(hold_raw)
    envelope = doc.get("envelope")
    if isinstance(envelope, dict):
        published = envelope.get("published")
        if isinstance(published, dict):
            envelope["published"] = {
                str(k): portable_artifact_ref(v, run_dir=run_dir, hold_dir=hold_path)
                for k, v in published.items()
            }
    return doc
