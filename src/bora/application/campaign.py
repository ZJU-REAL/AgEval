"""Campaign / matrix expansion (v0.11) — foreground serial Trials."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bora.application.run_command import run_task
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
    """Parse ``/parameters/x=[1,2]`` style matrix axis."""
    if "=" not in raw:
        raise ConfigError("campaign_matrix_invalid", "matrix must be pointer=json-array")
    pointer, _, arr = raw.partition("=")
    if not pointer.startswith("/"):
        raise ConfigError("campaign_matrix_invalid", "pointer must start with /")
    # Only allow parameters/* overrides for v0.11 MVP
    if not pointer.startswith("/parameters/"):
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
) -> dict[str, Any]:
    """Serially run each matrix variant via production run_task."""
    axes = [parse_matrix_arg(a) for a in matrix_args]
    variants = expand_matrix(axes)
    trials: list[dict[str, Any]] = []
    for idx, variant in enumerate(variants):
        # v0.11 MVP: matrix values are recorded; full override injection into lock
        # is deferred — each trial reuses same package and records variant metadata.
        code, result, details = await run_task(package_root, task_id)
        trials.append(
            {
                "trial_index": idx,
                "variant": variant,
                "exit_code": code,
                "status": result.status,
                "score": result.score,
                "evidence_path": result.evidence_path,
                "digest_note": details.get("run_dir"),
            }
        )
        if code == 2 and result.status == "ERROR" and not variant:
            break
    summary = {
        "campaign": True,
        "task_id": task_id,
        "trial_count": len(trials),
        "trials": trials,
        "all_pass": all(t.get("status") == "PASS" for t in trials) if trials else False,
    }
    return summary
