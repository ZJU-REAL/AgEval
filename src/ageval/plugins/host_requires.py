"""Execute declared ``host_requires`` and report a shipped bake recipe.

Core only runs this allowlisted contract. No plugin-id → extra tables.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ageval.plugins.manifest import HostRequire, PluginManifest
from ageval.plugins.store import list_installed, resolve_package_root

BAKE_REL = Path("docker") / "Dockerfile.bake"


def import_available(name: str) -> bool:
    """True when ``importlib.util.find_spec`` can see *name* (no import, no spawn)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError, ImportError):
        return False


def file_available(root: Path, rel: str) -> bool:
    """True when *rel* is a regular file under *root* (no ``..`` / absolute)."""
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        return False
    parts = Path(rel).parts
    if any(p in {"..", ""} for p in parts):
        return False
    try:
        base = root.resolve(strict=False)
        path = (base / rel).resolve(strict=False)
        path.relative_to(base)
    except (OSError, ValueError):
        return False
    return path.is_file()


def installed_plugin(plugin_id: str) -> tuple[PluginManifest, Path] | None:
    for entry in list_installed():
        if entry.plugin_id == plugin_id:
            root = resolve_package_root(entry)
            if not root.is_dir():
                return None
            from ageval.plugins.manifest import load_manifest

            return load_manifest(root), root
    return None


def bake_recipe_declared(manifest: PluginManifest, root: Path) -> bool:
    """True when the plugin ships a bake recipe the box build can consume."""
    del manifest
    return (root / BAKE_REL).is_file()


def evaluate_host_requires(
    requires: Sequence[HostRequire],
    *,
    root: Path | None,
    plugin_id: str,
) -> list[dict[str, Any]]:
    """One check dict per declared import/file. No secret values."""
    checks: list[dict[str, Any]] = []
    for item in requires:
        if item.import_name:
            ok = import_available(item.import_name)
            row: dict[str, Any] = {
                "id": "host_import",
                "ok": ok,
                "status": "ok" if ok else "missing",
                "import": item.import_name,
                "plugin": plugin_id,
            }
            if item.hint:
                row["hint"] = item.hint
            checks.append(row)
        if item.file:
            ok = bool(root) and file_available(root, item.file)
            row = {
                "id": "host_file",
                "ok": ok,
                "status": "ok" if ok else "missing",
                "file": item.file,
                "plugin": plugin_id,
            }
            if item.hint and not item.import_name:
                row["hint"] = item.hint
            checks.append(row)
    return checks


def locator_names_present(
    names: Sequence[str],
    environ: Mapping[str, str],
) -> tuple[bool, list[str]]:
    """Return (any present, present names). Values are never returned."""
    present: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        val = environ.get(name)
        if val is not None and str(val).strip():
            present.append(name)
    return (len(present) > 0, present)


def host_requires_satisfied(
    requires: Sequence[HostRequire],
    *,
    root: Path | None,
) -> bool:
    if not requires:
        return True
    for item in requires:
        if item.import_name and not import_available(item.import_name):
            return False
        if item.file and (root is None or not file_available(root, item.file)):
            return False
    return True
