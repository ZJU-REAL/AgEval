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
from bora.config.constants import DEFAULTS
from bora.config.digest import digest_payload
from bora.config.errors import (
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
from bora.config.overrides import apply_json_pointer, is_allowlisted_override_pointer
from bora.config.ports import PackageReader
from bora.config.profiles import (
    apply_binding_override,
    assert_slots_have_no_inline_binding,
    is_binding_override_pointer,
    merge_bindings_onto_slots,
    project_job_overlay,
)
from bora.config.provenance import merge_provenance, validate_provenance
from bora.config.validate import (
    collect_resolved_references,
    validate_document,
    validate_top_level_layout,
)
from bora.config.yaml_io import deep_merge, parse_yaml


def _resolve_extension_bindings(
    profiles_raw: list[Any],
) -> dict[str, dict[str, Any]] | None:
    """Resolve extension graphs for each locked profile.

    Failures propagate as ConfigError so ``bora lock`` fails closed on conflict
    or missing plugin provide.
    """
    if not profiles_raw:
        return None

    from bora.plugins.bootstrap import ensure_bootstrapped
    from bora.plugins.errors import ExtensionRegistryError
    from bora.plugins.lock_bind import extension_graph_to_lock
    from bora.plugins.protocol import intent_from_profile
    from bora.plugins.resolve import resolve as resolve_extensions

    registry = ensure_bootstrapped()
    out: dict[str, dict[str, Any]] = {}
    for profile in profiles_raw:
        if not isinstance(profile, Mapping):
            continue
        pid = profile.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        intent = intent_from_profile(profile)
        if not intent.profile_id:
            intent.profile_id = pid.strip()
        try:
            # Lock serialization does not need live SPI instances.
            graph = resolve_extensions(intent, registry, materialize=False)
        except ExtensionRegistryError as exc:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"extension resolve failed for profile {pid!r}: {exc}",
                location=f"/agent_profiles/{pid}/extension_bindings",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"extension resolve failed for profile {pid!r}: {exc}",
                location=f"/agent_profiles/{pid}/extension_bindings",
            ) from exc
        out[pid.strip()] = extension_graph_to_lock(graph)
    return out or None


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
        profile_bindings: Mapping[str, Mapping[str, object]] | None = None,
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
            Explicit overrides as a mapping of JSON Pointer → value.
            Parameter pointers apply after profile merge; ``/bindings/<role>/…``
            pointers apply to the job binding map before slot merge (#59).
        capabilities:
            Declaration-only catalog used for kind/format recognition.
        database_provenance:
            Optional Database-root ``provenance`` (suite default). Member
            ``task.yaml`` provenance fully replaces this when present.
        profile_bindings:
            Job agent/model bindings from Database ``profiles.yaml`` and/or
            CLI ``--profiles`` (role id → executor/entry/model/locator).
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

        # #68 Dataset shared/ bans + task top-level ``shared`` shadow ban.
        from bora.config.shared import infer_database_root_from_task, validate_shared_layout

        db_root = infer_database_root_from_task(root)
        if db_root is not None:
            from bora.config.database import load_database_manifest

            man = load_database_manifest(db_root)
            validate_shared_layout(db_root, tasks_root=man.tasks_root)

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

        from bora.config.checks import reject_env_interpolation, require_agent_profiles_list

        # Reject env-style interpolation markers so experiment semantics stay in yaml.
        reject_env_interpolation(text, what="task.yaml", location="task.yaml")

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

        # --- #59 job binding merge -------------------------------------------------
        # 1) Role slots from task.yaml must not embed executor/entry/model.
        slots_raw = require_agent_profiles_list(merged.get("agent_profiles") or [])
        assert_slots_have_no_inline_binding(slots_raw)

        bindings: dict[str, dict[str, Any]] = {
            str(k): dict(v) for k, v in (profile_bindings or {}).items() if isinstance(v, Mapping)
        }

        # 2) Split overrides: binding axes vs parameter leaves.
        param_overrides: dict[str, object] = {}
        if overrides:
            for pointer, value in overrides.items():
                pointer_s = str(pointer)
                if not is_allowlisted_override_pointer(pointer_s):
                    from bora.config.errors import ERROR_INVALID_OVERRIDE

                    raise ConfigError(
                        ERROR_INVALID_OVERRIDE,
                        f"pointer not allowlisted for override: {pointer_s}",
                        location=pointer_s,
                    )
                if is_binding_override_pointer(pointer_s):
                    apply_binding_override(bindings, pointer_s, value)
                    resolution.append(
                        ResolutionEntry(
                            source="cli-override",
                            pointer=pointer_s,
                            note="binding override",
                        )
                    )
                else:
                    param_overrides[pointer_s] = value

        if bindings:
            resolution.append(
                ResolutionEntry(
                    source="profiles.yaml",
                    pointer="/agent_profiles",
                    note="database/job profile bindings",
                )
            )

        # 3) Merge bindings onto slots (fail closed if a required role is unbound).
        if slots_raw:
            merged["agent_profiles"] = merge_bindings_onto_slots(slots_raw, bindings)
        else:
            merged["agent_profiles"] = []

        # 4) Parameter overrides after binding merge.
        if param_overrides:
            for pointer_s, value in param_overrides.items():
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
        profiles_raw = require_agent_profiles_list(merged.get("agent_profiles") or [])
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

        # Secret-free job overlay used for this lock (rehydrate / Leaderboard binding).
        role_ids = [
            str(p.get("id"))
            for p in profiles_raw
            if isinstance(p, dict) and p.get("id") is not None
        ]
        job_overlay_plain = project_job_overlay(bindings, role_ids=role_ids) if role_ids else None
        job_overlay_frozen = freeze(job_overlay_plain) if job_overlay_plain else None

        # Resolve per-profile extension graph into lock extension_bindings.
        extension_bindings_plain = _resolve_extension_bindings(profiles_raw)
        extension_bindings_frozen = (
            freeze(extension_bindings_plain) if extension_bindings_plain else None
        )
        if extension_bindings_plain:
            resolution.append(
                ResolutionEntry(
                    source="extension_registry",
                    pointer="/extension_bindings",
                    note="resolved extension point graph per profile",
                )
            )
            resolution_record = ResolutionRecord(entries=tuple(resolution))

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
            job_overlay=job_overlay_frozen,  # type: ignore[arg-type]
            extension_bindings=extension_bindings_frozen,  # type: ignore[arg-type]
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
            job_overlay=job_overlay_frozen,  # type: ignore[arg-type]
            extension_bindings=extension_bindings_frozen,  # type: ignore[arg-type]
        )
