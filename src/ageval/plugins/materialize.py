"""Explicit materialize of plugin README/skills (never silent .agents write)."""

from __future__ import annotations

import shutil
from pathlib import Path

from ageval.plugins.store import list_installed, resolve_package_root


class MaterializeError(Exception):
    def __init__(self, message: str, *, kind: str = "plugin_materialize_failed") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def materialize_docs(plugin_id: str, target: Path) -> list[str]:
    """Copy README.md and skills/ into *target*. Returns relative paths copied."""
    entry = next((p for p in list_installed() if p.plugin_id == plugin_id), None)
    if entry is None:
        raise MaterializeError(f"plugin not installed: {plugin_id}", kind="plugin_not_installed")
    root = resolve_package_root(entry)
    target = target.expanduser().resolve(strict=False)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    readme = root / "README.md"
    if readme.is_file():
        dest = target / "README.md"
        shutil.copy2(readme, dest)
        copied.append("README.md")
    skills = root / "skills"
    if skills.is_dir():
        dest_skills = target / "skills"
        if dest_skills.exists():
            shutil.rmtree(dest_skills)
        shutil.copytree(skills, dest_skills)
        copied.append("skills/")
    if not copied:
        raise MaterializeError(
            f"no README.md or skills/ in {root}",
            kind="plugin_docs_empty",
        )
    return copied
