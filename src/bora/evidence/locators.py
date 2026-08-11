"""Portable evidence locators for sealed Attempt / campaign products (#70).

Sealed JSON must never embed host absolute paths (home dirs, /var/folders, …).
Canonical form (option A): ``.bora/runs/<run_id>`` relative to the Database root.

Readers should accept this form, bare ``run_id`` directory names, and legacy
absolute paths (via ``extract_run_id``-style parsing).
"""

from __future__ import annotations

from pathlib import Path


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
