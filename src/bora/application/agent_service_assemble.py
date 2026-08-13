"""Single production assembly site for ParentAgentService.

L0 and L1 both call ``assemble_parent_agent_service`` so profile injection,
deadline, and invoke-timeout policy stay in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bora.config.model import thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.runtime.parent_agent_service import (
    ParentAgentService,
    resolve_invoke_timeout_seconds,
)


def read_wall_deadline(
    lock: Any,
    *,
    monotonic_now: float,
) -> tuple[float, float | None]:
    """Return ``(wall_seconds, deadline_monotonic|None)`` from locked limits."""
    try:
        wall_s = float(thaw(lock.limits).get("wall_time_seconds") or 0)
    except Exception:
        wall_s = 0.0
    deadline = (monotonic_now + wall_s) if wall_s > 0 else None
    return wall_s, deadline


def inject_service_profiles(
    profiles: list[Any],
    *,
    package_root: Path,
    workdir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Copy profiles and inject package/workdir context for executor materialize."""
    service_profiles: list[dict[str, Any]] = []
    for p in profiles:
        if not isinstance(p, dict):
            continue
        row = dict(p)
        opts = dict(row.get("options") or {}) if isinstance(row.get("options"), dict) else {}
        opts["_package_root"] = str(package_root)
        if workdir is not None:
            opts.setdefault("_workdir", str(workdir))
        row["options"] = opts
        service_profiles.append(row)
    return service_profiles


def assemble_parent_agent_service(
    *,
    profiles: list[Any],
    package_root: Path,
    attempt_id: str,
    inv_limit: int,
    params: dict[str, Any] | None,
    evidence_store: Any,
    deadline_monotonic: float | None,
    workdir: Path | str | None = None,
    require_actor_id: bool = False,
    validate_actor_profile: Any = None,
    resolve_placement: Any = None,
    l1_container_only: bool = False,
) -> tuple[ParentAgentService, float]:
    """Build the sole production ParentAgentService used by L0/L1 paths.

    Returns ``(service, invoke_timeout_seconds)``.
    """
    from bora.capabilities.quota import AgentInvocationQuota

    invoke_timeout = resolve_invoke_timeout_seconds(params if isinstance(params, dict) else {})
    service_profiles = inject_service_profiles(
        profiles,
        package_root=package_root,
        workdir=workdir,
    )
    kwargs: dict[str, Any] = {
        "profiles": service_profiles,
        "agent_invocation_limit": inv_limit,
        "attempt_id": attempt_id,
        "extension_registry": ensure_bootstrapped(),
        "invoke_quota": AgentInvocationQuota(limit=inv_limit),
        "evidence_store": evidence_store,
        "deadline_monotonic": deadline_monotonic,
        "invoke_timeout_seconds": invoke_timeout,
    }
    if require_actor_id:
        kwargs["require_actor_id"] = True
    if validate_actor_profile is not None:
        kwargs["validate_actor_profile"] = validate_actor_profile
    if resolve_placement is not None:
        kwargs["resolve_placement"] = resolve_placement
    if l1_container_only:
        kwargs["l1_container_only"] = True
    return ParentAgentService(**kwargs), invoke_timeout
