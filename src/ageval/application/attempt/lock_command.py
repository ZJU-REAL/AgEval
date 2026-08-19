"""Application use case for ``ageval lock``.

Resolves a Database member, invokes Config Core on ``task.yaml``, and projects a
public ``LockSummary`` dict (plus Database provenance). No side effects beyond
reading the package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ageval.config.capabilities import CapabilityCatalog
from ageval.config.database import load_database_manifest, resolve_task
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import LockedTaskConfig, locked_to_summary
from ageval.config.overrides import parse_set_override
from ageval.config.profiles import resolve_profile_bindings
from ageval.registry.resolve import resolve_database_root


class LockCommand:
    """Production lock use case assembled by the composition root."""

    def __init__(self, config_core: ConfigCore, capabilities: CapabilityCatalog) -> None:
        self._config_core = config_core
        self._capabilities = capabilities

    def run(
        self,
        *,
        database_root: Path | str | None = None,
        package_root: Path | str | None = None,
        task_id: str,
        set_overrides: Sequence[str] = (),
        variant: Mapping[str, object] | None = None,
        profiles_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Execute resolve + load_and_lock and return a JSON-serializable summary.

        Parameters
        ----------
        database_root:
            Preferred: Database root path or registry ref (``id@version`` /
            ``id@sha256:…``). Local paths resolve without registry.
        package_root:
            Deprecated alias for *database_root*.
        task_id:
            Member task id under the Database.
        profiles_path:
            Optional alternate ``profiles.yaml`` replacing Database-root defaults.
        """
        locked, extra = self.lock_with_provenance(
            database_root=database_root,
            package_root=package_root,
            task_id=task_id,
            set_overrides=set_overrides,
            variant=variant,
            profiles_path=profiles_path,
        )
        summary = locked_to_summary(locked).as_dict()
        summary.update(extra)
        return summary

    def lock_with_provenance(
        self,
        *,
        database_root: Path | str | None = None,
        package_root: Path | str | None = None,
        task_id: str,
        set_overrides: Sequence[str] = (),
        variant: Mapping[str, object] | None = None,
        profiles_path: Path | str | None = None,
    ) -> tuple[LockedTaskConfig, dict[str, str]]:
        """Same resolve + lock as ``run``, returning the frozen lock + provenance."""
        raw = database_root if database_root is not None else package_root
        if raw is None:
            msg = "database_root is required"
            raise TypeError(msg)

        root = resolve_database_root(raw)
        from ageval.application.attempt.env_bootstrap import load_host_env_files

        load_host_env_files(package_root=root)
        resolved = resolve_task(root, task_id)
        man = load_database_manifest(root)

        overrides: dict[str, object] = {}
        for raw_set in set_overrides:
            pointer, value = parse_set_override(raw_set)
            overrides[pointer] = value

        bindings = resolve_profile_bindings(root, profiles_path=profiles_path)

        locked = self._config_core.load_and_lock(
            resolved.task_dir,
            task_id,
            variant=variant,
            overrides=overrides or None,
            capabilities=self._capabilities,
            database_provenance=man.provenance,
            profile_bindings=bindings or None,
        )
        extra = {
            "database_id": resolved.database_id,
            "database_version": resolved.database_version,
        }
        return locked, extra
