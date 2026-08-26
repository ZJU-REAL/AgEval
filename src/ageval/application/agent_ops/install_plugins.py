"""Install plugins declared on an Agent binding (design/14).

Called after the agent cache write. Reuses ``ageval plugin install``
(``install_from_local`` / Hub fetch). Never rewrites profiles.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ageval.config.errors import ConfigError
from ageval.plugins.host_requires import evaluate_host_requires, installed_plugin
from ageval.plugins.install import InstalledItem, install_extracted_hub, install_from_local
from ageval.plugins.manifest import MANIFEST_NAMES, PluginManifestError, split_plugin_id
from ageval.plugins.plugin_requires import PluginRequiresError
from ageval.plugins.reserved import reserved_short_id
from ageval.plugins.store import load_index

HubFetch = Callable[[str], Path]


def plugin_ids_from_binding(binding: Mapping[str, Any]) -> list[str]:
    """Unique ``extensions[].plugin`` ids, declaration order."""
    rows = binding.get("extensions")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        plugin_id = str(row.get("plugin") or "").strip()
        if not plugin_id or plugin_id in seen:
            continue
        seen.add(plugin_id)
        out.append(plugin_id)
    return out


def install_declared_plugins(
    binding: Mapping[str, Any],
    *,
    agent_root: Path | None = None,
    hub_fetch: HubFetch | None = None,
) -> list[InstalledItem]:
    """Install each declared plugin or fail closed.

    Contrib ids (``acp``, ``docker``, …) are skipped. Cached plugins are
    ``already_present``. Missing source or unsatisfied ``host_requires``
    raises ``ConfigError``.
    """
    items: list[InstalledItem] = []
    for plugin_id in plugin_ids_from_binding(binding):
        item = _install_one(plugin_id, agent_root=agent_root, hub_fetch=hub_fetch)
        if item is not None:
            items.append(item)
    return items


def _install_one(
    plugin_id: str,
    *,
    agent_root: Path | None,
    hub_fetch: HubFetch | None,
) -> InstalledItem | None:
    if reserved_short_id(plugin_id) is not None:
        return None
    cached = load_index().find(plugin_id)
    if cached is not None:
        _assert_host_requires(plugin_id)
        return InstalledItem(
            plugin_id=cached.plugin_id,
            version=cached.version,
            digest=cached.digest,
            path=cached.path,
            status="already_present",
        )
    try:
        result = _fetch_and_install(plugin_id, agent_root=agent_root, hub_fetch=hub_fetch)
    except PluginRequiresError as exc:
        raise ConfigError(exc.kind, exc.message, location=plugin_id) from exc
    except PluginManifestError as exc:
        raise ConfigError(exc.kind, exc.message, location=plugin_id) from exc
    _assert_host_requires(plugin_id)
    for item in result.items:
        if item.plugin_id == plugin_id:
            return item
    entry = result.entry
    return InstalledItem(
        plugin_id=entry.plugin_id,
        version=entry.version,
        digest=entry.digest,
        path=entry.path,
        status="installed",
    )


def _fetch_and_install(
    plugin_id: str,
    *,
    agent_root: Path | None,
    hub_fetch: HubFetch | None,
) -> Any:
    org, _name = split_plugin_id(plugin_id)
    if org is not None:
        if hub_fetch is None:
            raise ConfigError(
                "plugin_requires_unsatisfied",
                f"plugin {plugin_id!r} needs a registry fetch",
                location=plugin_id,
            )
        extracted = hub_fetch(plugin_id)
        return install_extracted_hub(extracted, plugin_id=plugin_id, hub_fetch=hub_fetch)
    local = _local_plugin_dir(plugin_id, agent_root=agent_root)
    if local is None:
        raise ConfigError(
            "plugin_requires_unsatisfied",
            f"plugin {plugin_id!r} is not installed and has no local plugin directory",
            location=plugin_id,
        )
    return install_from_local(local, hub_fetch=hub_fetch)


def _assert_host_requires(plugin_id: str) -> None:
    found = installed_plugin(plugin_id)
    if found is None:
        raise ConfigError(
            "plugin_requires_unsatisfied",
            f"plugin {plugin_id!r} is not in the plugin index after install",
            location=plugin_id,
        )
    manifest, root = found
    missing = [
        row
        for row in evaluate_host_requires(manifest.host_requires, root=root, plugin_id=plugin_id)
        if not row.get("ok")
    ]
    if not missing:
        return
    raise ConfigError(
        "host_requires_unsatisfied",
        _host_requires_message(plugin_id, missing),
        location=plugin_id,
    )


def _host_requires_message(plugin_id: str, missing: list[dict[str, Any]]) -> str:
    """Plugin cache is not the host extra. Spell the missing import/file and hint."""
    parts: list[str] = []
    for row in missing:
        if row.get("import"):
            bit = f"import {row['import']!r} missing"
        elif row.get("file"):
            bit = f"file {row['file']!r} missing"
        else:
            bit = "requirement missing"
        hint = row.get("hint")
        if isinstance(hint, str) and hint.strip():
            bit = f"{bit} ({hint.strip()})"
        parts.append(bit)
    detail = "; ".join(parts) if parts else "host_requires unsatisfied"
    return (
        f"plugin {plugin_id!r} is in the plugin cache; this host cannot import/run it yet: {detail}"
    )


def _local_plugin_dir(plugin_id: str, *, agent_root: Path | None) -> Path | None:
    """Find a local ``ageval.plugin/1`` tree for a short plugin id."""
    _org, name = split_plugin_id(plugin_id)
    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.append(cwd / plugin_id)
    candidates.append(cwd / "plugins" / plugin_id)
    candidates.append(cwd / "plugins" / name)
    if agent_root is not None:
        root = agent_root.expanduser().resolve(strict=False)
        candidates.append(root.parent / name)
        for parent in [root, *root.parents]:
            candidates.append(parent / "plugins" / name)
            if (parent / "pyproject.toml").is_file() and (parent / "src" / "ageval").is_dir():
                break
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not _is_plugin_dir(resolved):
            continue
        try:
            from ageval.plugins.manifest import load_manifest

            manifest = load_manifest(resolved)
        except PluginManifestError:
            continue
        if manifest.plugin_id in {plugin_id, name}:
            return resolved
    return None


def _is_plugin_dir(path: Path) -> bool:
    return path.is_dir() and any((path / name).is_file() for name in MANIFEST_NAMES)
