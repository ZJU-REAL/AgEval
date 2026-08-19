"""Campaign / matrix expansion (v0.11) — foreground serial Trials."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ageval.application.composition import build_run_attempt
from ageval.config.errors import ConfigError


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
    from ageval.config.overrides import is_allowlisted_override_pointer

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

    *package_root* is the Dataset root. Pre-admits all variants by dry-lock
    (resolve + load_and_lock) before any Trial runs; writes an atomic campaign
    summary under the Dataset ``.ageval/campaigns/``.
    """
    from ageval.application.composition import build_lock_command
    from ageval.registry.resolve import resolve_dataset_root

    dataset_root = resolve_dataset_root(package_root)
    lock_command = build_lock_command()

    axes = [parse_matrix_arg(a) for a in matrix_args]
    variants = expand_matrix(axes)
    # Pre-admit: every variant must lock successfully before the first Trial.
    admitted: list[dict[str, Any]] = []
    for idx, variant in enumerate(variants):
        lock = lock_command.lock(
            dataset_root,
            task_id,
            overrides=variant if variant else None,
            profiles_path=profiles_path,
        ).lock
        admitted.append(
            {
                "trial_index": idx,
                "variant": variant,
                "digest": lock.digest,
                "dataset_id": lock.dataset_id,
                "trial_id": f"trial_plan_{idx}_{lock.digest[-12:]}",
            }
        )
    trials: list[dict[str, Any]] = []
    for plan in admitted:
        variant = plan["variant"]
        code, result = await build_run_attempt()(
            dataset_root,
            task_id,
            overrides=variant if variant else None,
            profiles_path=profiles_path,
        )
        from ageval.evidence.locators import portable_run_locator

        # Always re-normalize so a future abs regression cannot leak into campaign rows.
        candidates = (result.evidence_path, result.logs)
        portable = None
        for raw in candidates:
            if raw:
                portable = portable_run_locator(raw, dataset_root=dataset_root)
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
                "digest": plan["digest"],
            }
        )
        if code == 2 and result.status == "ERROR" and not variant:
            break
    digests = [t.get("digest") for t in trials if t.get("digest")]
    summary = {
        "campaign": True,
        "dataset_id": admitted[0]["dataset_id"] if admitted else "",
        "task_id": task_id,
        "trial_count": len(trials),
        "trials": trials,
        "all_pass": all(t.get("status") == "PASS" for t in trials) if trials else False,
        "unique_digests": len(set(digests)),
        "admission": "preflight_all_variants_then_serial",
        "admitted_count": len(admitted),
        "stop_on_config_error": True,
    }
    # Atomic summary write under Dataset root
    camp_dir = dataset_root / ".ageval" / "campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    out = camp_dir / f"summary_{task_id}_{len(admitted)}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    try:
        summary["summary_path"] = out.relative_to(dataset_root.resolve()).as_posix()
    except ValueError:
        summary["summary_path"] = f".ageval/campaigns/{out.name}"
    return summary
