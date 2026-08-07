"""Config Core façade: load, merge, validate, canonicalize, digest, freeze.

This module is the only normative reader of member ``task.yaml``. It never imports or
executes package-local Python, never expands environment variables as experiment
semantics, and never starts an Attempt.

Pure helpers: ``constants``, ``yaml_io``, ``overrides``, ``digest``, ``validate`` (chore #31).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bora.config.capabilities import CapabilityCatalog
from bora.config.constants import ALLOWLISTED_OVERRIDE_POINTERS, DEFAULTS
from bora.config.digest import digest_payload
from bora.config.errors import (
    ERROR_INVALID_OVERRIDE,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ConfigError,
)
from bora.config.model import (
    LockedTaskConfig,
    ResolutionEntry,
    ResolutionRecord,
    freeze,
)
from bora.config.overrides import apply_json_pointer
from bora.config.ports import PackageReader
from bora.config.provenance import merge_provenance, validate_provenance
from bora.config.validate import (
    collect_resolved_references,
    validate_document,
    validate_top_level_layout,
)
from bora.config.yaml_io import deep_merge, parse_yaml


class ConfigCore:
    """Normative Config Core façade."""

    def __init__(self, package_reader: PackageReader) -> None:
        self._reader = package_reader

    def load_and_lock(
        self,
        package_root: Path,
        task_id: str,
        *,
        variant: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        capabilities: CapabilityCatalog,
        database_provenance: Mapping[str, object] | None = None,
    ) -> LockedTaskConfig:
        """Read, merge, validate, canonicalize, digest, and freeze a task package.

        Parameters
        ----------
        package_root:
            Directory containing ``task.yaml`` (Database member task root).
        task_id:
            Must equal ``task.yaml`` ``task_id`` (operator-selected task).
        variant:
            Optional Campaign variant overlay (merge step 2). CLI does not expose
            this in v0.1; tests exercise the merge order.
        overrides:
            Explicit overrides as a mapping of JSON Pointer → value (merge step 3).
        capabilities:
            Declaration-only catalog used for kind/format recognition.
        database_provenance:
            Optional Database-root ``provenance`` (suite default). Member
            ``task.yaml`` provenance fully replaces this when present.
        """
        try:
            root = self._reader.resolve_root(package_root)
        except (OSError, FileNotFoundError) as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot open package root: {package_root}",
                location=str(package_root),
            ) from exc

        validate_top_level_layout(self._reader, root)

        if not self._reader.exists(root, "task.yaml"):
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "task.yaml not found",
                location="task.yaml",
            )

        try:
            text = self._reader.read_text(root, "task.yaml")
        except (OSError, ValueError) as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot read task.yaml: {exc}",
                location="task.yaml",
            ) from exc

        # Reject env-style interpolation markers so experiment semantics stay in yaml.
        if "${" in text or "os.environ" in text:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "environment variable interpolation is not allowed in task.yaml",
                location="task.yaml",
            )

        raw = parse_yaml(text)
        resolution: list[ResolutionEntry] = [
            ResolutionEntry(source="task.yaml", pointer="/", note="task document"),
        ]

        # Apply explicit defaults for missing top-level sections / known keys.
        merged = copy.deepcopy(raw)
        for key, default_value in DEFAULTS.items():
            if key not in merged or merged[key] is None:
                merged[key] = copy.deepcopy(default_value)
                resolution.append(
                    ResolutionEntry(source="default", pointer=f"/{key}", note="explicit default")
                )
            elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
                for d_key, d_val in default_value.items():
                    if d_key not in merged[key]:
                        merged[key][d_key] = copy.deepcopy(d_val)
                        resolution.append(
                            ResolutionEntry(
                                source="default",
                                pointer=f"/{key}/{d_key}",
                                note="explicit default",
                            )
                        )

        if variant:
            merged = deep_merge(merged, dict(variant))
            resolution.append(
                ResolutionEntry(source="campaign-variant", pointer="/", note="variant overlay")
            )

        if overrides:
            for pointer, value in overrides.items():
                pointer_s = str(pointer)
                if pointer_s not in ALLOWLISTED_OVERRIDE_POINTERS:
                    raise ConfigError(
                        ERROR_INVALID_OVERRIDE,
                        f"pointer not allowlisted for override: {pointer_s}",
                        location=pointer_s,
                    )
                apply_json_pointer(merged, pointer_s, value)
                resolution.append(
                    ResolutionEntry(
                        source="cli-override", pointer=pointer_s, note="explicit override"
                    )
                )

        validate_document(
            self._reader,
            merged,
            task_id=task_id,
            root=root,
            capabilities=capabilities,
        )
        resolved_refs = collect_resolved_references(merged, root)

        # Provenance: task fully replaces Database default; omit when neither set.
        task_prov_raw = merged.get("provenance")
        task_prov: dict[str, Any] | None = None
        if task_prov_raw is not None:
            task_prov = validate_provenance(task_prov_raw, location="/provenance")
            resolution.append(
                ResolutionEntry(
                    source="task.yaml",
                    pointer="/provenance",
                    note="task provenance",
                )
            )
        db_prov: dict[str, Any] | None = None
        if database_provenance is not None:
            db_prov = validate_provenance(
                dict(database_provenance), location="database:/provenance"
            )
            if task_prov is None:
                resolution.append(
                    ResolutionEntry(
                        source="database",
                        pointer="/provenance",
                        note="database default provenance",
                    )
                )
        effective_prov = merge_provenance(database=db_prov, task=task_prov)

        # Freeze section views.
        format_id = str(merged["format"])
        locked_task_id = str(merged["task_id"])
        harness = freeze(merged["harness"])
        parameters = freeze(merged.get("parameters") or {})
        provider = freeze(merged["provider"])
        profiles_raw = merged.get("agent_profiles") or []
        if not isinstance(profiles_raw, list):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "agent_profiles must be a list", location="/agent_profiles"
            )
        agent_profiles = tuple(freeze(p) for p in profiles_raw)
        environment = (
            freeze(merged["environment"]) if merged.get("environment") is not None else None
        )
        limits = freeze(merged["limits"])
        artifacts = freeze(merged["artifacts"])
        evaluation = freeze(merged["evaluation"])
        provenance_frozen = freeze(effective_prov) if effective_prov is not None else None
        resolution_record = ResolutionRecord(entries=tuple(resolution))
        resolved_references = freeze(resolved_refs)

        # Build digest over a stable payload without the digest field.
        provisional = LockedTaskConfig(
            format=format_id,
            task_id=locked_task_id,
            harness=harness,  # type: ignore[arg-type]
            parameters=parameters,  # type: ignore[arg-type]
            provider=provider,  # type: ignore[arg-type]
            agent_profiles=agent_profiles,  # type: ignore[arg-type]
            environment=environment,  # type: ignore[arg-type]
            limits=limits,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            evaluation=evaluation,  # type: ignore[arg-type]
            resolution=resolution_record,
            digest="",  # filled below
            resolved_references=resolved_references,  # type: ignore[arg-type]
            provenance=provenance_frozen,  # type: ignore[arg-type]
        )
        payload = provisional.canonical_payload()
        digest = digest_payload(payload)

        return LockedTaskConfig(
            format=format_id,
            task_id=locked_task_id,
            harness=harness,  # type: ignore[arg-type]
            parameters=parameters,  # type: ignore[arg-type]
            provider=provider,  # type: ignore[arg-type]
            agent_profiles=agent_profiles,  # type: ignore[arg-type]
            environment=environment,  # type: ignore[arg-type]
            limits=limits,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            evaluation=evaluation,  # type: ignore[arg-type]
            resolution=resolution_record,
            digest=digest,
            resolved_references=resolved_references,  # type: ignore[arg-type]
            provenance=provenance_frozen,  # type: ignore[arg-type]
        )
