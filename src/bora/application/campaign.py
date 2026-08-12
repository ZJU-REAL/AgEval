"""Campaign / matrix expansion (v0.11) — foreground serial Trials."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bora.application.composition import build_run_task
from bora.config.errors import ConfigError


@dataclass(frozen=True, slots=True)
class MatrixAxis:
    pointer: str
    values: tuple[Any, ...]


def expand_matrix(axes: list[MatrixAxis]) -> list[dict[str, Any]]:
    """Deterministic cartesian expansion; empty axes → single empty variant."""
    variants: list[dict[str, Any]] = [{}]
    for axis in axes:
        if not axis.values:
            raise ConfigError("campaign_matrix_empty_axis", f"empty axis {axis.pointer}")
        next_variants: list[dict[str, Any]] = []
        for base in variants:
            for val in axis.values:
                item = dict(base)
                item[axis.pointer] = val
                next_variants.append(item)
        variants = next_variants
    # Stable order by JSON of pointer/value pairs
    return sorted(variants, key=lambda d: json.dumps(d, sort_keys=True, default=str))


def parse_matrix_arg(raw: str) -> MatrixAxis:
    """Parse ``/parameters/x=[1,2]`` or ``/bindings/<role>/model=[…]`` matrix axis."""
    if "=" not in raw:
        raise ConfigError("campaign_matrix_invalid", "matrix must be pointer=json-array")
    pointer, _, arr = raw.partition("=")
    if not pointer.startswith("/"):
        raise ConfigError("campaign_matrix_invalid", "pointer must start with /")
    # #59: parameters/* and binding axes (/bindings/<role>/…)
    from bora.config.overrides import is_allowlisted_override_pointer

    if not is_allowlisted_override_pointer(pointer):
        raise ConfigError(
            "campaign_matrix_pointer_unsupported",
            f"unsupported matrix pointer: {pointer}",
        )
    try:
        values = json.loads(arr)
    except json.JSONDecodeError as exc:
        raise ConfigError("campaign_matrix_invalid", "matrix values must be JSON") from exc
    if not isinstance(values, list):
        raise ConfigError("campaign_matrix_invalid", "matrix values must be a JSON array")
    return MatrixAxis(pointer=pointer, values=tuple(values))


async def run_campaign(
    package_root: Path,
    task_id: str,
    *,
    matrix_args: list[str],
    profiles_path: Path | str | None = None,
) -> dict[str, Any]:
    """Serially run each matrix variant via production run_task.

    *package_root* is the Database root. Pre-admits all variants by dry-lock
    (resolve + load_and_lock) before any Trial runs; writes an atomic campaign
    summary under the Database ``.bora/campaigns/``.
    """
    from bora.adapters.package_fs import LocalPackageReader
    from bora.config.capabilities import DeclarationCapabilityCatalog
    from bora.config.database import load_database_manifest, resolve_task
    from bora.config.load_and_lock import ConfigCore
    from bora.config.profiles import resolve_profile_bindings
    from bora.registry.resolve import resolve_database_root

    database_root = resolve_database_root(package_root)
    resolved = resolve_task(database_root, task_id)
    task_dir = resolved.task_dir
    man = load_database_manifest(resolved.database_root)
    bindings = resolve_profile_bindings(resolved.database_root, profiles_path=profiles_path)

    axes = [parse_matrix_arg(a) for a in matrix_args]
    variants = expand_matrix(axes)
    # Pre-admit: every variant must lock successfully before first Trial.
    config = ConfigCore(package_reader=LocalPackageReader())
    admitted: list[dict[str, Any]] = []
    for idx, variant in enumerate(variants):
        lock = config.load_and_lock(
            task_dir,
            task_id,
            overrides=variant if variant else None,
            capabilities=DeclarationCapabilityCatalog(),
            database_provenance=man.provenance,
            profile_bindings=bindings or None,
        )
        admitted.append(
            {
                "trial_index": idx,
                "variant": variant,
                "digest": lock.digest,
                "trial_id": f"trial_plan_{idx}_{lock.digest[-12:]}",
            }
        )
    trials: list[dict[str, Any]] = []
    for plan in admitted:
        variant = plan["variant"]
        code, result, details = await build_run_task()(
            database_root,
            task_id,
            overrides=variant if variant else None,
            profile_bindings=bindings or None,
        )
        from bora.evidence.locators import portable_run_locator

        # Always re-normalize so a future abs regression cannot leak into campaign rows.
        candidates = (
            result.evidence_path,
            result.logs,
            details.get("run_dir"),
            details.get("logs"),
        )
        portable = None
        for raw in candidates:
            if raw:
                portable = portable_run_locator(raw, database_root=database_root)
                break
        trials.append(
            {
                "trial_index": plan["trial_index"],
                "trial_id": plan["trial_id"],
                "variant": variant,
                "exit_code": code,
                "status": result.status,
                "score": result.score,
                "evidence_path": portable,
                "run_dir": portable,
                "logs": portable,
                "digest": getattr(result, "digest", None)
                or details.get("digest")
                or plan["digest"],
            }
        )
        if code == 2 and result.status == "ERROR" and not variant:
            break
    digests = [t.get("digest") for t in trials if t.get("digest")]
    summary = {
        "campaign": True,
        "database_id": resolved.database_id,
        "task_id": task_id,
        "trial_count": len(trials),
        "trials": trials,
        "all_pass": all(t.get("status") == "PASS" for t in trials) if trials else False,
        "unique_digests": len(set(digests)),
        "admission": "preflight_all_variants_then_serial",
        "admitted_count": len(admitted),
        "stop_on_config_error": True,
    }
    # Atomic summary write under Database root
    camp_dir = database_root / ".bora" / "campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    out = camp_dir / f"summary_{task_id}_{len(admitted)}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    try:
        summary["summary_path"] = out.relative_to(database_root.resolve()).as_posix()
    except ValueError:
        summary["summary_path"] = f".bora/campaigns/{out.name}"
    return summary
