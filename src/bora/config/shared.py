"""Dataset-level ``shared/`` layout helpers (#65).

Design authority: ``docs/design/02-task-package-and-config.md`` (Dataset 级 shared/).
"""

from __future__ import annotations

from pathlib import Path

from bora.config.errors import ERROR_INVALID_PACKAGE, ConfigError

# Top-level names under shared/ that must not exist (ban gold/secrets confusion).
_FORBIDDEN_SHARED_TOP_LEVEL = frozenset(
    {
        "evaluation",  # gold lives only under tasks/*/evaluation/
        ".env",
    }
)


def shared_dir(database_root: Path) -> Path:
    return database_root.expanduser().resolve(strict=False) / "shared"


def shared_lib_dir(database_root: Path) -> Path:
    return shared_dir(database_root) / "lib"


def infer_database_root_from_task(task_dir: Path) -> Path | None:
    """Best-effort Database root from a member task directory.

    Standard layout: ``<database_root>/<tasks_root>/<task_id>/``. When the
    grandparent contains ``bora.yaml``, treat it as the Database root.
    """
    task_dir = task_dir.expanduser().resolve(strict=False)
    candidate = task_dir.parent.parent
    if (candidate / "bora.yaml").is_file():
        return candidate
    return None


def top_level_import_names(lib_dir: Path) -> set[str]:
    """Top-level Python import names under a ``lib/`` directory.

    Collects bare module stems (``foo.py`` → ``foo``) and package directories
    that contain ``__init__.py`` or any nested content used as a namespace.
    Skips ``__pycache__`` and private ``_*`` only when they are not importable
    packages authors would deliberately share — ``_*`` names are still checked
    if present as modules (collision risk is real).
    """
    if not lib_dir.is_dir():
        return set()
    names: set[str] = set()
    for child in lib_dir.iterdir():
        if child.name == "__pycache__" or child.name.endswith(".pyc"):
            continue
        if child.name.startswith("."):
            continue
        if child.is_file() and child.suffix == ".py":
            if child.name == "__init__.py":
                continue
            names.add(child.stem)
        elif child.is_dir():
            # Treat any non-cache directory as an importable package name.
            names.add(child.name)
    return names


def collect_shared_lib_names(database_root: Path) -> set[str]:
    return top_level_import_names(shared_lib_dir(database_root))


def collect_task_lib_names(task_dir: Path) -> set[str]:
    return top_level_import_names(task_dir / "lib")


def find_lib_collisions(
    database_root: Path,
    *,
    tasks_root: str = "tasks",
    task_ids: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Return collision triples ``(name, shared, tasks/<id>/lib)``.

    Empty list means no top-level import name clashes.
    """
    root = database_root.expanduser().resolve(strict=False)
    shared_names = collect_shared_lib_names(root)
    if not shared_names:
        return []

    if task_ids is None:
        tasks_dir = root / tasks_root
        if not tasks_dir.is_dir():
            return []
        task_ids = sorted(
            p.name for p in tasks_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
        )

    collisions: list[tuple[str, str, str]] = []
    for tid in task_ids:
        task_names = collect_task_lib_names(root / tasks_root / tid)
        for name in sorted(shared_names & task_names):
            collisions.append((name, "shared/lib", f"{tasks_root}/{tid}/lib"))
    return collisions


def validate_shared_layout(
    database_root: Path,
    *,
    tasks_root: str = "tasks",
    task_ids: list[str] | None = None,
) -> None:
    """Fail closed on forbidden ``shared/`` content or lib name collisions (#65).

    No-op when ``shared/`` is absent.
    """
    root = database_root.expanduser().resolve(strict=False)
    shared = root / "shared"
    if not shared.exists():
        return
    if not shared.is_dir():
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "shared must be a directory when present",
            location="shared",
        )

    for name in sorted(_FORBIDDEN_SHARED_TOP_LEVEL):
        bad = shared / name
        if bad.exists():
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"forbidden path under shared/: {name} "
                "(gold/secrets must not live under Dataset shared/)",
                location=f"shared/{name}",
            )

    # Also reject nested .env anywhere under shared/
    for env_file in shared.rglob(".env"):
        if env_file.is_file():
            try:
                rel = env_file.relative_to(root).as_posix()
            except ValueError:
                rel = "shared/.env"
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "host secrets must not live under shared/ (.env forbidden)",
                location=rel,
            )

    collisions = find_lib_collisions(root, tasks_root=tasks_root, task_ids=task_ids)
    if collisions:
        parts = [f"{name!r} in {shared_loc} and {task_loc}" for name, shared_loc, task_loc in collisions]
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            "shared/lib vs task lib top-level import name collision (ban): "
            + "; ".join(parts),
            location="shared/lib",
        )
