"""Application Capability checkpoint (v0.4) — no product CLI command."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ageval.capabilities.authority import AttemptCapabilityAuthority
from ageval.config.model import LockedTaskConfig
from ageval.runtime.identity import IdentityFactory


async def run_capability_probe(
    lock: LockedTaskConfig,
    *,
    declared_artifacts: frozenset[str] | None = None,
    declared_environment_actions: frozenset[str] | None = None,
    agent_invocation_limit: int | None = None,
    environment_action_limit: int | None = None,
    identity_factory: IdentityFactory | None = None,
) -> AttemptCapabilityAuthority:
    """Open Attempt-scoped authority from a locked config (declaration-driven)."""
    factory = identity_factory or IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    attempt = factory.new_attempt(trial)

    params: Mapping[str, Any] = lock.parameters
    limits = dict(lock.limits)
    arts = declared_artifacts
    if arts is None:
        publishable = list(lock.artifacts.get("publishable", ()))  # type: ignore[arg-type]
        arts = frozenset(
            str(item.get("id"))
            for item in publishable
            if isinstance(item, Mapping) and item.get("id")
        )

    return AttemptCapabilityAuthority(
        attempt=attempt,
        params=params,
        declared_artifacts=arts or frozenset(),
        declared_environment_actions=declared_environment_actions or frozenset(),
        agent_invocation_limit=agent_invocation_limit
        if agent_invocation_limit is not None
        else int(limits.get("agent_invocations", 1)),
        environment_action_limit=environment_action_limit
        if environment_action_limit is not None
        else int(limits.get("environment_actions", 0)),
    )
