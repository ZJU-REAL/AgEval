"""Application use case for ``bora lock``.

Resolves a Database member, invokes Config Core on ``task.yaml``, and projects a
public ``LockSummary`` dict (plus Database provenance). No side effects beyond
reading the package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bora.config.capabilities import CapabilityCatalog
from bora.config.database import load_database_manifest, resolve_task
from bora.config.load_and_lock import ConfigCore, parse_set_override
from bora.config.model import locked_to_summary
from bora.registry.resolve import resolve_database_root


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
        """
        raw = database_root if database_root is not None else package_root
        if raw is None:
            msg = "database_root is required"
            raise TypeError(msg)

        root = resolve_database_root(raw)
        resolved = resolve_task(root, task_id)
        man = load_database_manifest(root)

        overrides: dict[str, object] = {}
        for raw in set_overrides:
            pointer, value = parse_set_override(raw)
            overrides[pointer] = value

        locked = self._config_core.load_and_lock(
            resolved.task_dir,
            task_id,
            variant=variant,
            overrides=overrides or None,
            capabilities=self._capabilities,
            database_provenance=man.provenance,
        )
        summary = locked_to_summary(locked).as_dict()
        summary["database_id"] = resolved.database_id
        summary["database_version"] = resolved.database_version
        return summary
