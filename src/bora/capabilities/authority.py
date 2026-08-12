"""Shared Attempt capability authority with pre-effect gates and hard ceilings.

v0.4 is in-process only. Real Agent/Environment adapters are unavailable;
requests are rejected before any external effect starts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from bora.capabilities.errors import (
    ERROR_CLOSED,
    ERROR_CROSS_ATTEMPT,
    ERROR_QUOTA_EXCEEDED,
    ERROR_UNAVAILABLE,
    ERROR_UNDECLARED,
    CapabilityError,
)
from bora.capabilities.quota import AgentInvocationQuota
from bora.runtime.identity import AttemptIdentity


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """Authorization decision receipt (no secret material)."""

    attempt_id: str
    kind: str
    action: str
    allowed: bool
    sequence: int
    reason: str = ""


@dataclass
class AttemptCapabilityAuthority:
    """Open/closed + scope + quota gate for one Attempt."""

    attempt: AttemptIdentity
    params: Mapping[str, Any]
    declared_artifacts: frozenset[str] = field(default_factory=frozenset)
    declared_environment_actions: frozenset[str] = field(default_factory=frozenset)
    agent_invocation_limit: int = 1
    environment_action_limit: int = 0
    # Optional shared ledger with ParentAgentService (same Attempt).
    invoke_quota: AgentInvocationQuota | None = None
    _open: bool = field(default=True, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _env_used: int = field(default=0, init=False)
    _seq: int = field(default=0, init=False)
    _receipts: list[CapabilityDecision] = field(default_factory=list, init=False)
    # Test sink start counters (prove pre-effect denial).
    agent_sink_starts: int = field(default=0, init=False)
    env_sink_starts: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        if self.invoke_quota is None:
            self.invoke_quota = AgentInvocationQuota(limit=self.agent_invocation_limit)

    @property
    def is_open(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False

    def parameter_view(self) -> Mapping[str, Any]:
        self._require_open()
        return self.params

    def workspace_path(self, relative: str) -> str:
        """Return a logical package-relative path string (no host mount)."""
        self._require_open()
        if relative.startswith("/") or ".." in relative.split("/"):
            raise CapabilityError(ERROR_UNDECLARED, f"path not allowed: {relative}")
        return relative

    async def publish_artifact(self, artifact_id: str, payload: bytes) -> CapabilityDecision:
        """Authorize declared artifact publish (in-memory receipt only in v0.4)."""
        async with self._lock:
            self._require_open()
            if artifact_id not in self.declared_artifacts:
                return self._deny("artifact", f"publish:{artifact_id}", ERROR_UNDECLARED)
            return self._allow("artifact", f"publish:{artifact_id}")

    async def emit_event(
        self, name: str, data: Mapping[str, Any] | None = None
    ) -> CapabilityDecision:
        async with self._lock:
            self._require_open()
            _ = data
            return self._allow("event", name)

    async def authorize_agent_invoke(self, profile_id: str) -> CapabilityDecision:
        """Pre-effect authorize one agent invocation against hard ceiling."""
        async with self._lock:
            self._require_open()
            assert self.invoke_quota is not None
            if not self.invoke_quota.try_consume():
                return self._deny("agent", f"invoke:{profile_id}", ERROR_QUOTA_EXCEEDED)
            return self._allow("agent", f"invoke:{profile_id}")

    async def authorize_environment_action(self, action_id: str) -> CapabilityDecision:
        async with self._lock:
            self._require_open()
            if action_id not in self.declared_environment_actions:
                return self._deny("environment", action_id, ERROR_UNDECLARED)
            if self._env_used >= self.environment_action_limit:
                return self._deny("environment", action_id, ERROR_QUOTA_EXCEEDED)
            self._env_used += 1
            return self._allow("environment", action_id)

    async def invoke_agent_unavailable(self, profile_id: str) -> None:
        """Production path: agent capability is declared unavailable (no sink)."""
        async with self._lock:
            self._require_open()
            raise CapabilityError(
                ERROR_UNAVAILABLE,
                f"agent executor unavailable in v0.4: {profile_id}",
            )

    async def run_agent_with_test_sink(self, profile_id: str, sink: Any) -> CapabilityDecision:
        """Test helper path: authorize then start sink (proves pre-effect order)."""
        decision = await self.authorize_agent_invoke(profile_id)
        if not decision.allowed:
            return decision
        self.agent_sink_starts += 1
        await sink()
        return decision

    def receipts(self) -> tuple[CapabilityDecision, ...]:
        return tuple(self._receipts)

    def _require_open(self) -> None:
        if not self._open:
            raise CapabilityError(ERROR_CLOSED, "capability bundle is closed")

    def _allow(self, kind: str, action: str) -> CapabilityDecision:
        self._seq += 1
        d = CapabilityDecision(
            attempt_id=self.attempt.value,
            kind=kind,
            action=action,
            allowed=True,
            sequence=self._seq,
        )
        self._receipts.append(d)
        return d

    def _deny(self, kind: str, action: str, code: str) -> CapabilityDecision:
        self._seq += 1
        d = CapabilityDecision(
            attempt_id=self.attempt.value,
            kind=kind,
            action=action,
            allowed=False,
            sequence=self._seq,
            reason=code,
        )
        self._receipts.append(d)
        return d

    def bind_attempt(self, attempt: AttemptIdentity) -> None:
        if attempt != self.attempt:
            raise CapabilityError(ERROR_CROSS_ATTEMPT, "authority attempt mismatch")
