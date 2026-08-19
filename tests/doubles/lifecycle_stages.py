"""Scriptable LifecycleStages double for Core 2 acceptance tests.

Does not create processes, workspaces, Harness terminals, Evaluator results,
or PASS claims — only identity-bound generic PhaseFact objects.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ageval.runtime.identity import AttemptIdentity
from ageval.runtime.lifecycle import LifecyclePhase
from ageval.runtime.outcomes import PhaseFact, PhaseStatus


@dataclass
class ScriptedLifecycleStages:
    """Configurable stage double for unit and acceptance tests."""

    # phase name → status to return (default succeeded)
    fail_at: LifecyclePhase | None = None
    fail_status: PhaseStatus = PhaseStatus.FAILED
    fail_message: str = "scripted stage failure"
    hang_at: LifecyclePhase | None = None
    hang_seconds: float = 60.0
    cleanup_raises: bool = False
    cleanup_status: PhaseStatus = PhaseStatus.SUCCEEDED
    cleanup_message: str = ""
    wrong_identity_at: LifecyclePhase | None = None
    foreign_attempt: AttemptIdentity | None = None
    cleanup_calls: int = field(default=0, init=False)
    calls: list[str] = field(default_factory=list)

    async def _stage(self, attempt: AttemptIdentity, phase: LifecyclePhase) -> PhaseFact:
        self.calls.append(phase.value)
        if self.hang_at == phase:
            await asyncio.sleep(self.hang_seconds)
        if self.wrong_identity_at == phase and self.foreign_attempt is not None:
            return PhaseFact(
                attempt=self.foreign_attempt,
                phase=phase,
                status=PhaseStatus.SUCCEEDED,
            )
        if self.fail_at == phase:
            return PhaseFact(
                attempt=attempt,
                phase=phase,
                status=self.fail_status,
                message=self.fail_message,
            )
        return PhaseFact(attempt=attempt, phase=phase, status=PhaseStatus.SUCCEEDED)

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact:
        return await self._stage(attempt, LifecyclePhase.PREPARE)

    async def run(self, attempt: AttemptIdentity) -> PhaseFact:
        return await self._stage(attempt, LifecyclePhase.RUN)

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact:
        return await self._stage(attempt, LifecyclePhase.SEAL)

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact:
        return await self._stage(attempt, LifecyclePhase.EVALUATE)

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact:
        return await self._stage(attempt, LifecyclePhase.BIND)

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact:
        self.cleanup_calls += 1
        self.calls.append("cleanup")
        if self.hang_at == LifecyclePhase.CLEANUP:
            await asyncio.sleep(self.hang_seconds)
        if self.cleanup_raises:
            raise RuntimeError("scripted cleanup boom")
        return PhaseFact(
            attempt=attempt,
            phase=LifecyclePhase.CLEANUP,
            status=self.cleanup_status,
            message=self.cleanup_message,
        )
