"""Suite config fingerprint for Leaderboard comparability (#42).

Computed at suite summary write time from each task's agent_profiles topology.
Never invents suite-level PASS. Fingerprint materials exclude credentials/secrets
(api_key locators and values are omitted).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Fields allowed in actors_summary / fingerprint material (no secrets).
_ACTOR_KEYS = ("profile_id", "entry", "model")


def _profile_entry(profile: Mapping[str, Any]) -> str:
    """Stable entry id: ACP ``options.entry``, else executor kind."""
    options = profile.get("options")
    if isinstance(options, Mapping):
        entry = options.get("entry")
        if entry is not None and str(entry).strip():
            return str(entry).strip()
    executor = profile.get("executor")
    if executor is not None and str(executor).strip():
        return str(executor).strip()
    return ""


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
        rows.append({"profile_id": pid, "entry": entry, "model": model})
    rows.sort(key=lambda r: (r["profile_id"], r["entry"], r["model"]))
    return rows


def _canonical_bytes(actors: Sequence[Mapping[str, str]]) -> bytes:
    material = [{k: str(a.get(k) or "") for k in _ACTOR_KEYS} for a in actors]
    return json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint_for_actors(actors: Sequence[Mapping[str, str]]) -> str:
    """``sha256:<hex>`` over canonical (sorted) actors_summary JSON."""
    # Always re-canonicalize so call order does not affect the digest.
    sorted_actors = actors_summary_from_profiles(list(actors))
    digest = hashlib.sha256(_canonical_bytes(sorted_actors)).hexdigest()
    return f"sha256:{digest}"


def topology_key(actors: Sequence[Mapping[str, str]]) -> str:
    """Role topology only (profile_id + entry); model ignored for shape compare."""
    shape = [{"profile_id": a.get("profile_id") or "", "entry": a.get("entry") or ""} for a in actors]
    shape.sort(key=lambda r: (r["profile_id"], r["entry"]))
    return json.dumps(shape, sort_keys=True, separators=(",", ":"))


def derive_labels(actors: Sequence[Mapping[str, str]]) -> tuple[str, str]:
    """Default agent_label / model_label from actors (suite-level display)."""
    if not actors:
        return "", ""
    if len(actors) == 1:
        a = actors[0]
        agent = a.get("entry") or a.get("profile_id") or ""
        model = a.get("model") or ""
        return agent, model
    agent = "+".join(a.get("profile_id") or a.get("entry") or "?" for a in actors)
    models = [a.get("model") or "" for a in actors]
    if all(models) and len(set(models)) == 1:
        model = models[0]
    else:
        model = "+".join(m or "?" for m in models)
    return agent, model


def compute_suite_config_fields(
    per_task_actors: Sequence[Sequence[Mapping[str, str]] | list[dict[str, str]]],
) -> dict[str, Any]:
    """Aggregate per-task actors into suite fingerprint fields.

    Parameters
    ----------
    per_task_actors:
        One actors_summary list per task that participated in the suite.
        Empty list (no tasks) → empty fingerprint, homogeneous True.

    Returns
    -------
    dict
        ``config_fingerprint``, ``config_homogeneous``, ``actors_summary``,
        and default ``agent_label`` / ``model_label`` (may be empty strings).
    """
    normalized: list[list[dict[str, str]]] = []
    for raw in per_task_actors:
        if not raw:
            normalized.append([])
            continue
        # Re-canonicalize each task's list
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

    # Full config equality (topology + models) across tasks
    keys = [_canonical_bytes(a) for a in normalized]
    homogeneous = all(k == keys[0] for k in keys)

    # Representative actors: first task when homogeneous; empty when not
    # (Hub must not present a single misleading combo for mixed suites).
    if homogeneous:
        actors = list(normalized[0])
    else:
        # Still expose the first task's actors for diagnostics, but mark false.
        actors = list(normalized[0])

    agent_label, model_label = derive_labels(actors) if homogeneous else ("", "")
    # Fingerprint is always over the representative actors list; consumers must
    # check config_homogeneous before treating it as a comparable combo id.
    return {
        "config_fingerprint": fingerprint_for_actors(actors),
        "config_homogeneous": homogeneous,
        "actors_summary": actors,
        "agent_label": agent_label,
        "model_label": model_label,
    }


def load_actors_from_run_lock(
    database_root: Path,
    run_id: str | None,
) -> list[dict[str, str]] | None:
    """Read actors from Attempt ``lock.json`` under ``.bora/runs/<run_id>/``.

    Returns None if missing/unreadable (caller may fall back to live lock).
    """
    if not run_id or not str(run_id).strip():
        return None
    path = database_root / ".bora" / "runs" / str(run_id) / "lock.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    profiles = data.get("profiles") or data.get("agent_profiles") or []
    if not isinstance(profiles, list):
        return None
    # evidence lock rows use ``id``; normalize to actors_summary
    return actors_summary_from_profiles(profiles)


def load_actors_from_task_lock(
    database_root: Path,
    task_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Lock a task (same overrides as suite) and project agent_profiles.

    Used when run evidence lock is unavailable (e.g. stub runners in tests).
    Never includes api_key in the projection.
    """
    from bora.adapters.package_fs import LocalPackageReader
    from bora.config.capabilities import DeclarationCapabilityCatalog
    from bora.config.database import load_database_manifest, resolve_task
    from bora.config.load_and_lock import ConfigCore
    from bora.config.model import thaw

    resolved = resolve_task(database_root, task_id)
    man = load_database_manifest(resolved.database_root)
    config = ConfigCore(package_reader=LocalPackageReader())
    lock = config.load_and_lock(
        resolved.task_dir,
        task_id,
        overrides=overrides,
        capabilities=DeclarationCapabilityCatalog(),
        database_provenance=man.provenance,
    )
    profiles = thaw(lock.agent_profiles)
    if not isinstance(profiles, list):
        return []
    return actors_summary_from_profiles(profiles)


def collect_suite_config(
    database_root: Path,
    task_rows: Sequence[Mapping[str, Any]],
    *,
    overrides: dict[str, Any] | None = None,
    task_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build suite config fingerprint fields from task result rows + package.

    Prefers Attempt ``lock.json`` per ``run_id``; falls back to live
    ``load_and_lock`` for that task_id; empty actors if both fail.
    """
    per_task: list[list[dict[str, str]]] = []
    ids = list(task_ids) if task_ids is not None else []
    if not ids:
        ids = [str(r.get("task_id") or "") for r in task_rows]

    # Index rows by task_id for run_id lookup
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in task_rows:
        tid = str(row.get("task_id") or "")
        if tid:
            by_id[tid] = row

    for tid in ids:
        if not tid:
            per_task.append([])
            continue
        row = by_id.get(tid)
        actors: list[dict[str, str]] | None = None
        if row is not None:
            actors = load_actors_from_run_lock(database_root, row.get("run_id") if isinstance(row.get("run_id"), str) else None)
            if actors is None and row.get("run_id"):
                actors = load_actors_from_run_lock(database_root, str(row.get("run_id")))
        if actors is None:
            try:
                actors = load_actors_from_task_lock(
                    database_root, tid, overrides=overrides
                )
            except Exception:  # noqa: BLE001 — fingerprint must not fail suite write
                actors = []
        per_task.append(actors)

    return compute_suite_config_fields(per_task)
