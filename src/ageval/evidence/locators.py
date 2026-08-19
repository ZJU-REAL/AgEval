"""Portable evidence locators for sealed Attempt / campaign products (#70).

Sealed JSON must never embed host absolute paths (home dirs, /var/folders, …).
Canonical form (option A): ``.ageval/runs/<run_id>`` relative to the Dataset root.

Readers should accept this form, bare ``run_id`` directory names, and legacy
absolute paths (via ``extract_run_id``-style parsing).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def default_runs_root(dataset_root: Path | str) -> Path:
    """Dataset-root Attempt evidence directory: ``<db>/.ageval/runs``."""
    return Path(dataset_root) / ".ageval" / "runs"


def default_suite_runs_root(dataset_root: Path | str) -> Path:
    """Dataset-root suite job directory: ``<db>/.ageval/suite-runs``."""
    return Path(dataset_root) / ".ageval" / "suite-runs"


def safe_id_segment(value: str, *, field: str) -> str:
    """Single path segment (job_id / task_id / run_id); reject traversal."""
    from ageval.config.errors import ConfigError

    text = (value or "").strip()
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or ".." in text
        or text.startswith(".")
    ):
        raise ConfigError(
            "invalid_package",
            f"invalid {field}: {value!r}",
            location=field,
        )
    return text


def portable_run_locator(
    run_dir: Path | str,
    *,
    dataset_root: Path | str | None = None,
) -> str:
    """Return a portable locator for an Attempt evidence directory.

    Preference order:
    1. Relative path under *dataset_root* (typically ``.ageval/runs/<run_id>``).
    2. Suffix ``.ageval/runs/<run_id>`` extracted from an absolute path.
    3. Bare directory name (last path component) when it looks like a run id.
    4. As a last resort, the string form of *run_dir* only if it is already
       relative and does not start with a host root — never expanduser homes.
    """
    path = Path(run_dir)
    db = Path(dataset_root).expanduser().resolve(strict=False) if dataset_root else None

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
    if ".ageval" in parts and "runs" in parts:
        try:
            i = parts.index(".ageval")
            if i + 2 < len(parts) and parts[i + 1] == "runs":
                return "/".join(parts[i : i + 3])
        except ValueError:
            pass
        # longer: .ageval/runs/<id>/...
        try:
            i = list(parts).index("runs")
            if i > 0 and parts[i - 1] == ".ageval" and i + 1 < len(parts):
                return f".ageval/runs/{parts[i + 1]}"
        except ValueError:
            pass

    name = path.name
    if name and name not in {".", ".."} and not _looks_like_host_root(path):
        # Prefer .ageval/runs/<name> when name looks like a run directory.
        if name.startswith("sha256_") or "_run_" in name or name.startswith("run_"):
            return f".ageval/runs/{name}"
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
    dataset_root: Path | str,
    run_id: str,
    *,
    task_id: str | None = None,
    require_task_match: bool = True,
) -> Path:
    """Locate Attempt evidence for *run_id* under the Dataset root sandbox.

    Lookup order mirrors the former viewer helper:
    1. ``{dataset}/.ageval/runs/{run_id}``
    2. ``{dataset}/{tasks_root}/{task_id}/.ageval/runs/{run_id}`` when task_id given
    3. Bounded scan under ``tasks/*/.ageval/runs/{run_id}``

    Raises ``ConfigError`` when no candidate is found (or task_id mismatches).
    """
    import contextlib
    import json

    from ageval.config.dataset import load_dataset_manifest
    from ageval.config.errors import ConfigError

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
                "path escapes dataset sandbox",
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

    root = Path(dataset_root).expanduser().resolve(strict=False)
    rid = _safe_segment(run_id, field="run_id")
    tid = _safe_segment(task_id, field="task_id") if task_id else None

    candidates: list[Path] = []
    primary = root / ".ageval" / "runs" / rid
    if primary.is_dir():
        candidates.append(primary)

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_dataset_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    if ".." in Path(tasks_root_name).parts or tasks_root_name.startswith(("/", "\\")):
        tasks_root_name = "tasks"

    if tid:
        task_local = root / tasks_root_name / tid / ".ageval" / "runs" / rid
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
            cand = child / ".ageval" / "runs" / rid
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


def resolve_attempt_run_dir(dataset_root: Path | str, run_id: str) -> Path:
    """Resolve ``.ageval/runs/<run_id>`` under the Dataset root; fail closed."""
    from ageval.config.errors import ConfigError

    text = (run_id or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text or ".." in text:
        raise ConfigError(
            "invalid_package",
            f"invalid run_id: {run_id!r}",
            location="run_id",
        )
    root = Path(dataset_root).expanduser().resolve(strict=False)
    runs_root = (root / ".ageval" / "runs").resolve(strict=False)
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
    dataset_root: Path | str,
    locator: Path | str | None,
) -> Path | None:
    """Resolve a portable (or legacy absolute) locator to an on-disk run directory.

    Returns ``None`` when *locator* is empty or cannot be resolved under the
    Dataset root (legacy abs outside the root still returns the abs Path if it
    exists — operator recovery).
    """
    if locator is None:
        return None
    text = str(locator).strip()
    if not text:
        return None
    root = Path(dataset_root).expanduser().resolve(strict=False)
    path = Path(text)

    if path.is_absolute():
        resolved = path.expanduser().resolve(strict=False)
        if resolved.is_dir():
            return resolved
        # Fall through: maybe abs path is dead but portable form can be derived
        portable = portable_run_locator(path, dataset_root=root)
        cand = root / portable
        if cand.is_dir():
            return cand
        return resolved if resolved.exists() else None

    # Relative / portable
    cand = (root / path).resolve(strict=False)
    if cand.is_dir():
        return cand
    # Bare run_id
    bare = root / ".ageval" / "runs" / path.name
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
    Never seals host temp roots (``/var/folders``, ``/tmp/ageval-artifacts-…``).
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
