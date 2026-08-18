"""Binding-aware host vs L1 feasibility probe (``bora lock|run --probe``).

Observational: does not invoke an Agent, bake an image, or write lock digest
fields. Core only executes plugin-declared ``host_requires``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from bora.adapters.acp_registry import readiness_for
from bora.adapters.executor_capabilities import get_capabilities
from bora.adapters.executor_inventory import FIRST_PARTY_KINDS
from bora.application.attempt.lock_command import LockCommand
from bora.application.plugin_ops.image_contribute_bake import selected_contribute_plugin_ids
from bora.config.model import LockedTaskConfig, locked_to_summary, thaw
from bora.config.profiles import acp_entry_from_binding
from bora.plugins.host_requires import (
    evaluate_host_requires,
    installed_plugin,
    l1_bake_declared,
    locator_names_present,
)
from bora.plugins.plugin_requires import evaluate_plugin_requires
from bora.runtime.offline import is_offline_agent

DockerProbe = Callable[[], bool]


def docker_daemon_reachable() -> bool:
    """True when ``docker info`` succeeds. ``BORA_SKIP_DOCKER=1`` is not reachable."""
    if os.environ.get("BORA_SKIP_DOCKER") == "1":
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def provider_path(lock: LockedTaskConfig) -> tuple[str, str]:
    raw = lock.provider.get("kind") if lock.provider else None
    kind = str(raw or "local").strip() or "local"
    path = "l1" if kind == "docker" else "l0"
    return kind, path


def bound_bindings(lock: LockedTaskConfig) -> list[dict[str, Any]]:
    overlay = thaw(lock.job_overlay) or {}
    bindings = overlay.get("bindings") if isinstance(overlay, Mapping) else None
    if not isinstance(bindings, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for role, row in bindings.items():
        if not isinstance(row, Mapping):
            continue
        kind = row.get("executor")
        if not kind:
            continue
        item: dict[str, Any] = {"role": str(role), "executor": str(kind)}
        api_key = row.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            item["api_key"] = api_key.strip()
        entry = acp_entry_from_binding(row)
        if entry:
            item["entry"] = entry
        rows.append(item)
    return rows


def bound_extension_plugins(lock: LockedTaskConfig) -> list[dict[str, str]]:
    """Every ``extensions[].plugin`` (and executor) named on the locked job."""
    overlay = thaw(lock.job_overlay) or {}
    bindings = overlay.get("bindings") if isinstance(overlay, Mapping) else None
    if not isinstance(bindings, Mapping):
        return []
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for role, row in bindings.items():
        if not isinstance(row, Mapping):
            continue
        role_id = str(role)
        candidates: list[str] = []
        extensions = row.get("extensions")
        if isinstance(extensions, Sequence) and not isinstance(extensions, (str, bytes)):
            for item in extensions:
                if isinstance(item, Mapping):
                    plugin = str(item.get("plugin") or "").strip()
                    if plugin:
                        candidates.append(plugin)
        executor = str(row.get("executor") or "").strip()
        if executor:
            candidates.append(executor)
        for plugin in candidates:
            key = (role_id, plugin)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"role": role_id, "plugin": plugin})
    return rows


def _locator_names_for(binding: Mapping[str, Any], kind: str) -> list[str]:
    declared = binding.get("api_key")
    if isinstance(declared, str) and declared.strip():
        return [declared.strip()]
    caps = get_capabilities(kind)
    if caps is None:
        return []
    return [n for n in caps.credential_env_names if n]


def _probe_external(
    *,
    binding: Mapping[str, Any],
    path: str,
    environ: Mapping[str, str],
    selected_contribute: Sequence[str],
) -> list[dict[str, Any]]:
    kind = str(binding["executor"])
    found = installed_plugin(kind)
    checks: list[dict[str, Any]] = [
        {
            "id": "plugin_installed",
            "ok": found is not None,
            "plugin": kind,
            "role": binding["role"],
        }
    ]
    if found is None:
        return checks
    manifest, root = found
    if path == "l0":
        checks.extend(
            evaluate_host_requires(
                manifest.host_requires,
                root=root,
                plugin_id=kind,
            )
        )
    else:
        selected = kind in selected_contribute
        bake_file = l1_bake_declared(manifest, root)
        checks.append(
            {
                "id": "l1_contribute_selected",
                "ok": selected,
                "plugin": kind,
                "role": binding["role"],
            }
        )
        checks.append(
            {
                "id": "l1_bake_declared",
                "ok": selected and bake_file,
                "plugin": kind,
                "role": binding["role"],
            }
        )
    names = _locator_names_for(binding, kind)
    if names:
        ok, present = locator_names_present(names, environ)
        checks.append(
            {
                "id": "credential_locator",
                "ok": ok,
                "plugin": kind,
                "role": binding["role"],
                "names": list(names),
                "present": present,
            }
        )
    return checks


def _probe_first_party(
    *,
    binding: Mapping[str, Any],
    path: str,
    environ: Mapping[str, str],
    which: Callable[[str], str | None] | None,
) -> list[dict[str, Any]]:
    kind = str(binding["executor"])
    role = binding["role"]
    checks: list[dict[str, Any]] = []
    if kind == "acp" and path == "l0":
        entry = binding.get("entry")
        if isinstance(entry, str) and entry.strip():
            try:
                from bora.adapters.acp_registry import load_acp_entries

                desc = load_acp_entries()[entry.strip()]
                ready = readiness_for(desc, which=which)
                checks.append(
                    {
                        "id": "acp_entry",
                        "ok": ready["readiness"] == "ready",
                        "entry_id": entry.strip(),
                        "role": role,
                        "status": ready["readiness"],
                    }
                )
            except KeyError:
                checks.append(
                    {
                        "id": "acp_entry",
                        "ok": False,
                        "entry_id": entry.strip(),
                        "role": role,
                        "status": "unknown_entry",
                    }
                )
    names = _locator_names_for(binding, kind)
    if names:
        ok, present = locator_names_present(names, environ)
        checks.append(
            {
                "id": "credential_locator",
                "ok": ok,
                "plugin": kind,
                "role": role,
                "names": list(names),
                "present": present,
            }
        )
    return checks


def _probe_extension_plugins(lock: LockedTaskConfig) -> list[dict[str, Any]]:
    """plugin_installed + plugin_requires for every bound extension (L0 and L1)."""
    checks: list[dict[str, Any]] = []
    seen_plugins: set[str] = set()
    for row in bound_extension_plugins(lock):
        plugin_id = row["plugin"]
        if plugin_id in seen_plugins:
            continue
        seen_plugins.add(plugin_id)
        if plugin_id in FIRST_PARTY_KINDS:
            checks.append(
                {
                    "id": "plugin_installed",
                    "ok": True,
                    "plugin": plugin_id,
                    "role": row["role"],
                    "source": "first-party",
                }
            )
            continue
        found = installed_plugin(plugin_id)
        checks.append(
            {
                "id": "plugin_installed",
                "ok": found is not None,
                "plugin": plugin_id,
                "role": row["role"],
            }
        )
        if found is None:
            continue
        manifest, _root = found
        checks.extend(evaluate_plugin_requires(manifest.plugin_requires, plugin_id=plugin_id))
    return checks


def probe_locked(
    lock: LockedTaskConfig,
    *,
    environ: Mapping[str, str] | None = None,
    docker_reachable: DockerProbe | None = None,
    which: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Build the observational probe object for an already-locked task."""
    env = environ if environ is not None else os.environ
    provider_kind, path = provider_path(lock)
    bindings = bound_bindings(lock)
    selected_contribute = selected_contribute_plugin_ids(lock) if path == "l1" else ()
    checks: list[dict[str, Any]] = []
    if path == "l1":
        docker_ok = (docker_reachable or docker_daemon_reachable)()
        checks.append({"id": "docker_daemon", "ok": docker_ok})
    for binding in bindings:
        kind = str(binding["executor"])
        if kind in FIRST_PARTY_KINDS:
            checks.extend(
                _probe_first_party(
                    binding=binding,
                    path=path,
                    environ=env,
                    which=which,
                )
            )
        else:
            checks.extend(
                _probe_external(
                    binding=binding,
                    path=path,
                    environ=env,
                    selected_contribute=selected_contribute,
                )
            )
    checks.extend(_probe_extension_plugins(lock))
    ready = all(bool(c.get("ok")) for c in checks)
    return {
        "ready": ready,
        "path": path,
        "provider_kind": provider_kind,
        "offline_agent": is_offline_agent(),
        "bindings": [{"role": b["role"], "executor": b["executor"]} for b in bindings],
        "checks": checks,
    }


class ProbeCommand:
    """Production ``--probe`` use case assembled by the composition root."""

    def __init__(self, lock_command: LockCommand) -> None:
        self._lock = lock_command

    def run(
        self,
        *,
        database_root: Path | str | None = None,
        package_root: Path | str | None = None,
        task_id: str,
        set_overrides: Sequence[str] = (),
        variant: Mapping[str, object] | None = None,
        profiles_path: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        docker_reachable: DockerProbe | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        locked, extra = self._lock.lock_with_provenance(
            database_root=database_root,
            package_root=package_root,
            task_id=task_id,
            set_overrides=set_overrides,
            variant=variant,
            profiles_path=profiles_path,
        )
        if environ is None:
            from bora.application.attempt.env_bootstrap import load_host_env_files
            from bora.registry.resolve import resolve_database_root

            raw = database_root if database_root is not None else package_root
            if raw is not None:
                load_host_env_files(package_root=resolve_database_root(raw))
        summary = locked_to_summary(locked).as_dict()
        summary.update(extra)
        probe = probe_locked(
            locked,
            environ=environ,
            docker_reachable=docker_reachable,
            which=which,
        )
        summary["probe"] = probe
        return summary, bool(probe["ready"])
