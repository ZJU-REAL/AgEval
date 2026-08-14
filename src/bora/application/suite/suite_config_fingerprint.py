"""Suite config fingerprint for Leaderboard comparability (#42 + #59).

#59: Leaderboard job axis is Database ``profiles.yaml`` (job_overlay), not
per-task role-slot topology. Different tasks may use different role *ids*;
agent×model bindings are distributed by one suite-level profiles document.

Fingerprint materials exclude credentials/secrets (api_key values never appear;
locators may appear in job_overlay but are omitted from the digest).
Never invents suite-level PASS.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Fields allowed in actors_summary / fingerprint material (no secrets).
_ACTOR_KEYS = ("profile_id", "entry", "executor", "model", "options")

# Builtin executor kinds are not marketplace plugins (Hub plugin tab).
_BUILTIN_EXECUTOR_KINDS = frozenset({"acp", "openai-http"})
_SKIP_PLUGIN_IDS = frozenset({"default", "acp", "openai-http"})


def _profile_entry(profile: Mapping[str, Any]) -> str:
    """Display id: ACP ``options.entry``, else plugin ``options.agent``, else kind."""
    options = profile.get("options")
    if isinstance(options, Mapping):
        for key in ("entry", "agent"):
            val = options.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    executor = profile.get("executor")
    if executor is not None and str(executor).strip():
        return str(executor).strip()
    return ""


def _profile_options(profile: Mapping[str, Any]) -> dict[str, Any]:
    from bora.config.profiles import secret_free_options

    raw = profile.get("options")
    return secret_free_options(raw if isinstance(raw, Mapping) else None)


def actors_summary_from_profiles(
    profiles: Sequence[Mapping[str, Any]] | Sequence[Any] | None,
) -> list[dict[str, str]]:
    """Project agent_profiles into a sorted, secret-free actors summary.

    Each item: ``{profile_id, entry, model}``. Order is by profile_id for
    stable fingerprints. Accepts raw ``agent_profiles`` rows or already
    projected actors_summary dicts (idempotent).
    """
    if not profiles:
        return []
    rows: list[dict[str, str]] = []
    for raw in profiles:
        if not isinstance(raw, Mapping):
            continue
        pid = str(raw.get("id") or raw.get("profile_id") or "").strip()
        # Prefer already-projected ``entry``; else derive from options/executor.
        if raw.get("entry") is not None and str(raw.get("entry")).strip():
            entry = str(raw.get("entry")).strip()
        else:
            entry = _profile_entry(raw)
        model = str(raw.get("model") or "").strip()
        executor = str(raw.get("executor") or "").strip()
        existing_opts = raw.get("options")
        if isinstance(existing_opts, str) and existing_opts.strip():
            options_s = existing_opts.strip()
        else:
            options = _profile_options(raw)
            options_s = (
                json.dumps(options, sort_keys=True, separators=(",", ":"), default=str)
                if options
                else ""
            )
        row: dict[str, str] = {"profile_id": pid, "entry": entry, "model": model}
        if executor:
            row["executor"] = executor
        label = str(raw.get("label") or "").strip()
        if label:
            row["label"] = label
        if options_s:
            row["options"] = options_s
        rows.append(row)
    rows.sort(key=lambda r: (r["profile_id"], r["entry"], r["model"]))
    return rows


def actors_summary_from_job_overlay(
    overlay: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Project secret-free job_overlay.bindings into actors_summary rows."""
    if not isinstance(overlay, Mapping):
        return []
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for role_id, raw in bindings.items():
        if not isinstance(raw, Mapping):
            continue
        rid = str(role_id).strip()
        if not rid:
            continue
        entry = _profile_entry(raw)
        model = str(raw.get("model") or "").strip()
        rows.append({"id": rid, "entry": entry, "model": model, **dict(raw)})
    return actors_summary_from_profiles(rows)


def _canonical_bytes(actors: Sequence[Mapping[str, str]]) -> bytes:
    material = [{k: str(a.get(k) or "") for k in _ACTOR_KEYS} for a in actors]
    return json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint_for_actors(actors: Sequence[Mapping[str, str]]) -> str:
    """``sha256:<hex>`` over canonical (sorted) actors_summary JSON."""
    # Always re-canonicalize so call order does not affect the digest.
    sorted_actors = actors_summary_from_profiles(list(actors))
    digest = hashlib.sha256(_canonical_bytes(sorted_actors)).hexdigest()
    return f"sha256:{digest}"


def _plugin_ref(plugin_id: str, version: str | None = None) -> dict[str, str] | None:
    pid = plugin_id.strip()
    if not pid or pid.casefold() in _SKIP_PLUGIN_IDS:
        return None
    row = {"plugin_id": pid}
    if version is not None and str(version).strip():
        row["version"] = str(version).strip()
    return row


def plugins_from_extension_bindings(
    bindings: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Secret-free plugin_id[+version] from lock ``extension_bindings``."""
    if not isinstance(bindings, Mapping):
        return []
    found: dict[str, dict[str, str]] = {}

    def _take(raw: Mapping[str, Any]) -> None:
        plugin = raw.get("plugin") or raw.get("plugin_id")
        if not isinstance(plugin, str):
            return
        ver = raw.get("version")
        ref = _plugin_ref(plugin, str(ver) if ver is not None else None)
        if ref is None:
            return
        prev = found.get(ref["plugin_id"])
        if prev is None or (ref.get("version") and not prev.get("version")):
            found[ref["plugin_id"]] = ref

    for subtree in bindings.values():
        if not isinstance(subtree, Mapping):
            continue
        # Per-profile map: slot → provide row or on-chain.
        slots = subtree
        if "kind" in subtree and ("plugin" in subtree or "chain" in subtree):
            slots = {"_": subtree}
        for row in slots.values():
            if not isinstance(row, Mapping):
                continue
            if row.get("kind") == "on" or "chain" in row:
                chain = row.get("chain")
                if isinstance(chain, list):
                    for item in chain:
                        if isinstance(item, Mapping):
                            _take(item)
                continue
            _take(row)
    return sorted(found.values(), key=lambda r: r["plugin_id"])


def plugins_from_job_overlay(overlay: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Infer marketplace plugin ids from job_overlay executor kinds."""
    if not isinstance(overlay, Mapping):
        return []
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping):
        return []
    found: dict[str, dict[str, str]] = {}
    for raw in bindings.values():
        if not isinstance(raw, Mapping):
            continue
        executor = raw.get("executor")
        if not isinstance(executor, str):
            continue
        kind = executor.strip()
        if not kind or kind.casefold() in _BUILTIN_EXECUTOR_KINDS:
            continue
        ref = _plugin_ref(kind)
        if ref is not None:
            found[ref["plugin_id"]] = ref
    return sorted(found.values(), key=lambda r: r["plugin_id"])


def merge_plugin_refs(*groups: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Union plugin refs; prefer a row that already has version."""
    found: dict[str, dict[str, str]] = {}
    for group in groups:
        for raw in group:
            if not isinstance(raw, Mapping):
                continue
            pid = str(raw.get("plugin_id") or "").strip()
            if not pid:
                continue
            ref = _plugin_ref(pid, str(raw.get("version") or "") or None)
            if ref is None:
                continue
            prev = found.get(pid)
            if prev is None or (ref.get("version") and not prev.get("version")):
                found[pid] = ref
    return sorted(found.values(), key=lambda r: r["plugin_id"])


def plugins_from_run_lock(
    database_root: Path,
    run_id: str | None,
) -> list[dict[str, str]]:
    data = load_run_lock_doc(database_root, run_id)
    if data is None:
        return []
    bindings = data.get("extension_bindings")
    return plugins_from_extension_bindings(bindings if isinstance(bindings, Mapping) else None)


def fingerprint_for_job_overlay(overlay: Mapping[str, Any] | None) -> str:
    """Fingerprint the suite job binding axis (profiles.yaml / job_overlay).

    Digests role → (entry, model) only — no api_key / secrets.
    """
    actors = actors_summary_from_job_overlay(overlay)
    return fingerprint_for_actors(actors)


def _binding_role_key(binding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    opts = _profile_options(binding)
    return (
        str(binding.get("executor") or "").strip(),
        _profile_entry(binding),
        str(binding.get("model") or "").strip(),
        json.dumps(opts, sort_keys=True, separators=(",", ":"), default=str),
    )


def job_overlays_compatible(
    suite_overlay: Mapping[str, Any] | None,
    per_task: Sequence[Mapping[str, Any] | None],
) -> bool:
    """True when every task overlay agrees with the suite job binding map.

    No-agent tasks (empty/missing overlay) are ignored. Role-topology differences
    (which role *ids* a task uses) do **not** break compatibility — only a
    conflicting entry/model for the same role id does (#59).
    """
    suite_bindings: Mapping[str, Any] = {}
    if isinstance(suite_overlay, Mapping):
        raw = suite_overlay.get("bindings")
        if isinstance(raw, Mapping):
            suite_bindings = raw

    for ov in per_task:
        if not isinstance(ov, Mapping):
            continue
        bindings = ov.get("bindings")
        if not isinstance(bindings, Mapping) or not bindings:
            continue
        for role_id, binding in bindings.items():
            if not isinstance(binding, Mapping):
                continue
            rid = str(role_id)
            suite_b = suite_bindings.get(rid)
            if not isinstance(suite_b, Mapping):
                # Task used a role not in suite profiles map → incompatible
                return False
            if _binding_role_key(binding) != _binding_role_key(suite_b):
                return False
    return True


def topology_key(actors: Sequence[Mapping[str, str]]) -> str:
    """Role topology only (profile_id + entry); model ignored for shape compare."""
    shape = [
        {"profile_id": a.get("profile_id") or "", "entry": a.get("entry") or ""} for a in actors
    ]
    shape.sort(key=lambda r: (r["profile_id"], r["entry"]))
    return json.dumps(shape, sort_keys=True, separators=(",", ":"))


def derive_labels(actors: Sequence[Mapping[str, str]]) -> tuple[str, str]:
    """Default agent_label / model_label from actors (suite / Jobs / Hub).

    Display only: ``label`` → ACP ``entry`` → ``executor``. Never ``options.agent``.
    """
    from bora.config.profiles import display_agent_name, join_display_names

    if not actors:
        return "", ""
    agents = [display_agent_name(a) for a in actors]
    models = [str(a.get("model") or "").strip() for a in actors]
    return join_display_names(agents), join_display_names(models)


def compute_suite_config_fields(
    per_task_actors: Sequence[Sequence[Mapping[str, str]] | list[dict[str, str]]],
    *,
    job_overlay: Mapping[str, Any] | None = None,
    per_task_overlays: Sequence[Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Aggregate suite fingerprint fields.

    #59 Leaderboard axis is ``job_overlay`` (profiles.yaml bindings). Role-slot
    topology may differ across tasks without making the suite incomparable.

    When *job_overlay* is provided, fingerprint/labels/homogeneous are derived
    from that binding map. *per_task_actors* remains for observational display
    of roles actually used when overlay is empty.
    """
    # --- Preferred path: suite-level job binding (#59) -----------------------
    if isinstance(job_overlay, Mapping) and isinstance(job_overlay.get("bindings"), Mapping):
        actors = actors_summary_from_job_overlay(job_overlay)
        overlays = list(per_task_overlays or [])
        homogeneous = job_overlays_compatible(job_overlay, overlays)
        agent_label, model_label = derive_labels(actors) if homogeneous else ("", "")
        return {
            "config_fingerprint": fingerprint_for_job_overlay(job_overlay),
            "config_homogeneous": homogeneous,
            "actors_summary": actors,
            "agent_label": agent_label,
            "model_label": model_label,
            "job_overlay": dict(job_overlay),
        }

    # --- Fallback: no suite profiles (all-empty / legacy) --------------------
    normalized: list[list[dict[str, str]]] = []
    for raw in per_task_actors:
        if not raw:
            normalized.append([])
            continue
        as_maps = [dict(a) for a in raw if isinstance(a, Mapping)]
        normalized.append(actors_summary_from_profiles(as_maps))

    if not normalized:
        empty: list[dict[str, str]] = []
        fp = fingerprint_for_actors(empty)
        return {
            "config_fingerprint": fp,
            "config_homogeneous": True,
            "actors_summary": empty,
            "agent_label": "",
            "model_label": "",
        }

    keys = [_canonical_bytes(a) for a in normalized]
    # Empty-agent tasks do not break binding homogeneity.
    non_empty_keys = [k for k, a in zip(keys, normalized, strict=True) if a]
    if not non_empty_keys:
        homogeneous = True
        actors: list[dict[str, str]] = []
    else:
        homogeneous = all(k == non_empty_keys[0] for k in non_empty_keys)
        actors = list(next(a for a in normalized if a))

    agent_label, model_label = derive_labels(actors) if homogeneous else ("", "")
    return {
        "config_fingerprint": fingerprint_for_actors(actors),
        "config_homogeneous": homogeneous,
        "actors_summary": actors,
        "agent_label": agent_label,
        "model_label": model_label,
    }


def load_run_lock_doc(
    database_root: Path,
    run_id: str | None,
) -> dict[str, Any] | None:
    """Load Attempt ``lock.json`` under ``.bora/runs/<run_id>/`` if present."""
    if not run_id or not str(run_id).strip():
        return None
    from bora.evidence.locators import default_runs_root

    path = default_runs_root(database_root) / str(run_id) / "lock.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_actors_from_run_lock(
    database_root: Path,
    run_id: str | None,
) -> list[dict[str, str]] | None:
    """Read actors from Attempt ``lock.json`` under ``.bora/runs/<run_id>/``.

    Returns None if missing/unreadable (caller may fall back to live lock).
    """
    data = load_run_lock_doc(database_root, run_id)
    if data is None:
        return None
    profiles = data.get("profiles") or data.get("agent_profiles") or []
    if not isinstance(profiles, list):
        return None
    return actors_summary_from_profiles(profiles)


def load_job_overlay_from_run_lock(
    database_root: Path,
    run_id: str | None,
) -> dict[str, Any] | None:
    """Secret-free ``job_overlay`` from Attempt lock (#59), if recorded."""
    data = load_run_lock_doc(database_root, run_id)
    if data is None:
        return None
    overlay = data.get("job_overlay")
    return dict(overlay) if isinstance(overlay, dict) else None


def load_actors_from_task_lock(
    database_root: Path,
    task_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    profiles_path: Path | str | None = None,
) -> list[dict[str, str]]:
    """Lock a task (same overrides as suite) and project agent_profiles."""
    from bora.adapters.package_fs import LocalPackageReader
    from bora.config.capabilities import DeclarationCapabilityCatalog
    from bora.config.database import load_database_manifest, resolve_task
    from bora.config.load_and_lock import ConfigCore
    from bora.config.model import thaw
    from bora.config.profiles import resolve_profile_bindings

    resolved = resolve_task(database_root, task_id)
    man = load_database_manifest(resolved.database_root)
    bindings = resolve_profile_bindings(resolved.database_root, profiles_path=profiles_path)
    config = ConfigCore(package_reader=LocalPackageReader())
    lock = config.load_and_lock(
        resolved.task_dir,
        task_id,
        overrides=overrides,
        capabilities=DeclarationCapabilityCatalog(),
        database_provenance=man.provenance,
        profile_bindings=bindings or None,
    )
    profiles = thaw(lock.agent_profiles)
    if not isinstance(profiles, list):
        return []
    return actors_summary_from_profiles(profiles)


def load_job_overlay_from_task_lock(
    database_root: Path,
    task_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    profiles_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Live-lock a task and project secret-free job_overlay (#59)."""
    from bora.adapters.package_fs import LocalPackageReader
    from bora.config.capabilities import DeclarationCapabilityCatalog
    from bora.config.database import load_database_manifest, resolve_task
    from bora.config.load_and_lock import ConfigCore
    from bora.config.model import thaw
    from bora.config.profiles import resolve_profile_bindings

    resolved = resolve_task(database_root, task_id)
    man = load_database_manifest(resolved.database_root)
    bindings = resolve_profile_bindings(resolved.database_root, profiles_path=profiles_path)
    config = ConfigCore(package_reader=LocalPackageReader())
    lock = config.load_and_lock(
        resolved.task_dir,
        task_id,
        overrides=overrides,
        capabilities=DeclarationCapabilityCatalog(),
        database_provenance=man.provenance,
        profile_bindings=bindings or None,
    )
    if lock.job_overlay is None:
        return None
    overlay = thaw(lock.job_overlay)
    return dict(overlay) if isinstance(overlay, dict) else None


def _suite_level_job_overlay(
    database_root: Path,
    *,
    overrides: dict[str, Any] | None = None,
    profiles_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Full Database profiles.yaml (+ binding overrides) as secret-free overlay."""
    from bora.config.profiles import (
        apply_binding_override,
        is_binding_override_pointer,
        project_job_overlay,
        resolve_profile_bindings,
    )

    try:
        bindings = resolve_profile_bindings(database_root, profiles_path=profiles_path)
    except Exception:  # noqa: BLE001
        return None
    if overrides:
        for pointer, value in overrides.items():
            ptr = str(pointer)
            if is_binding_override_pointer(ptr):
                try:
                    apply_binding_override(bindings, ptr, value)
                except Exception:  # noqa: BLE001
                    continue
    if not bindings:
        return None
    return project_job_overlay(bindings)


def collect_suite_config(
    database_root: Path,
    task_rows: Sequence[Mapping[str, Any]],
    *,
    overrides: dict[str, Any] | None = None,
    task_ids: Sequence[str] | None = None,
    profiles_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build suite config fingerprint fields from task result rows + package.

    Suite job axis = Database ``profiles.yaml`` (optional CLI ``--profiles`` /
    ``/bindings/*`` overrides). Per-task role topology may differ freely (#59).
    """
    per_task: list[list[dict[str, str]]] = []
    overlays: list[dict[str, Any] | None] = []
    ids = list(task_ids) if task_ids is not None else []
    if not ids:
        ids = [str(r.get("task_id") or "") for r in task_rows]

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in task_rows:
        tid = str(row.get("task_id") or "")
        if tid:
            by_id[tid] = row

    plugin_groups: list[list[dict[str, str]]] = []
    for tid in ids:
        if not tid:
            per_task.append([])
            overlays.append(None)
            continue
        row = by_id.get(tid)
        actors: list[dict[str, str]] | None = None
        overlay: dict[str, Any] | None = None
        run_id: str | None = None
        if row is not None:
            rid = row.get("run_id")
            if isinstance(rid, str) and rid.strip():
                run_id = rid
            elif rid is not None:
                run_id = str(rid)
            actors = load_actors_from_run_lock(database_root, run_id)
            overlay = load_job_overlay_from_run_lock(database_root, run_id)
            plugin_groups.append(plugins_from_run_lock(database_root, run_id))
        if actors is None:
            try:
                actors = load_actors_from_task_lock(
                    database_root,
                    tid,
                    overrides=overrides,
                    profiles_path=profiles_path,
                )
            except Exception:  # noqa: BLE001
                actors = []
        if overlay is None:
            try:
                overlay = load_job_overlay_from_task_lock(
                    database_root,
                    tid,
                    overrides=overrides,
                    profiles_path=profiles_path,
                )
            except Exception:  # noqa: BLE001
                overlay = None
        per_task.append(actors)
        overlays.append(overlay)

    suite_overlay = _suite_level_job_overlay(
        database_root, overrides=overrides, profiles_path=profiles_path
    )
    # Prefer full suite profiles map; fall back to union of task overlays.
    if suite_overlay is None:
        non_null = [o for o in overlays if isinstance(o, dict) and o.get("bindings")]
        if non_null:
            # Union bindings by role (first wins); locators only already.
            merged: dict[str, Any] = {}
            for ov in non_null:
                bindings = ov.get("bindings") if isinstance(ov, Mapping) else None
                if not isinstance(bindings, Mapping):
                    continue
                for rid, b in bindings.items():
                    if rid not in merged and isinstance(b, Mapping):
                        merged[str(rid)] = dict(b)
            if merged:
                suite_overlay = {"bindings": merged}

    fields = compute_suite_config_fields(
        per_task,
        job_overlay=suite_overlay,
        per_task_overlays=overlays,
    )
    fields["plugins"] = merge_plugin_refs(
        *plugin_groups,
        plugins_from_job_overlay(suite_overlay),
    )
    return fields
