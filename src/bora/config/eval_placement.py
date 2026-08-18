"""L1 evaluator placement on top of ``evaluation.tmpfs_mb`` (#133)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bora.config.constants import DEFAULT_EVAL_TMPFS_MB
from bora.config.errors import ERROR_INVALID_SCHEMA, ConfigError

PLACEMENT_STAGING = "staging"
PLACEMENT_WRITABLE = "writable"
PLACEMENTS = frozenset({PLACEMENT_STAGING, PLACEMENT_WRITABLE})

NETWORK_NONE = "none"
NETWORK_BRIDGE = "bridge"
NETWORKS = frozenset({NETWORK_NONE, NETWORK_BRIDGE})

TIMEOUT_ABS_MAX = 3600.0
WORKDIR_ENV = "BORA_EVAL_WORKDIR"
WORKDIR_PATH = "/tmp/eval-work"

_DEFAULT_TIMEOUT = {
    PLACEMENT_STAGING: 90.0,
    PLACEMENT_WRITABLE: 300.0,
}


@dataclass(frozen=True, slots=True)
class EvalPlacement:
    mode: str
    timeout_seconds: float
    tmpfs_mb: int
    tmpfs_exec: bool
    network: str = NETWORK_NONE
    reuse_attempt: bool = False

    @property
    def tmpfs_spec(self) -> str:
        exec_flag = "exec" if self.tmpfs_exec else "noexec"
        return f"/tmp:rw,{exec_flag},nosuid,size={self.tmpfs_mb}m"


def validate_evaluation_extras(
    evaluation: dict[str, Any],
    *,
    wall_time_seconds: float | None,
) -> None:
    """Validate placement / timeout / network / reuse_attempt. ``tmpfs_mb`` stays in validate.py."""
    resolve_eval_placement(evaluation, wall_time_seconds=wall_time_seconds)


def resolve_eval_placement(
    evaluation: dict[str, Any] | None,
    *,
    wall_time_seconds: float | None = None,
) -> EvalPlacement:
    doc = evaluation or {}
    raw_mode = doc.get("placement", PLACEMENT_STAGING)
    if raw_mode is None:
        raw_mode = PLACEMENT_STAGING
    if not isinstance(raw_mode, str) or raw_mode not in PLACEMENTS:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"evaluation.placement must be one of {sorted(PLACEMENTS)}",
            location="/evaluation/placement",
        )
    mode = raw_mode

    network = doc.get("network")
    if network is None:
        network = NETWORK_NONE
    if not isinstance(network, str) or network not in NETWORKS:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "evaluation.network must be none|bridge",
            location="/evaluation/network",
        )

    raw_reuse = doc.get("reuse_attempt")
    if raw_reuse is None:
        reuse_attempt = False
    elif isinstance(raw_reuse, bool):
        reuse_attempt = raw_reuse
    else:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "evaluation.reuse_attempt must be a boolean",
            location="/evaluation/reuse_attempt",
        )

    tmpfs = doc.get("tmpfs_mb", DEFAULT_EVAL_TMPFS_MB)
    if not isinstance(tmpfs, int) or isinstance(tmpfs, bool) or tmpfs < 1:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "evaluation.tmpfs_mb must be a positive integer",
            location="/evaluation/tmpfs_mb",
        )

    timeout = float(_DEFAULT_TIMEOUT[mode])
    explicit = "timeout_seconds" in doc
    if explicit:
        raw_t = doc["timeout_seconds"]
        if isinstance(raw_t, bool) or not isinstance(raw_t, int | float):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "evaluation.timeout_seconds must be a number",
                location="/evaluation/timeout_seconds",
            )
        timeout = float(raw_t)
        if timeout < 1:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "evaluation.timeout_seconds must be >= 1",
                location="/evaluation/timeout_seconds",
            )
    wall = float(wall_time_seconds) if wall_time_seconds and wall_time_seconds > 0 else None
    cap = min(wall, TIMEOUT_ABS_MAX) if wall is not None else TIMEOUT_ABS_MAX
    if explicit and timeout > cap:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"evaluation.timeout_seconds exceeds cap {cap:g}",
            location="/evaluation/timeout_seconds",
        )
    if not explicit and timeout > cap:
        timeout = cap

    return EvalPlacement(
        mode=mode,
        timeout_seconds=timeout,
        tmpfs_mb=tmpfs,
        tmpfs_exec=(mode == PLACEMENT_WRITABLE),
        network=network,
        reuse_attempt=reuse_attempt,
    )
