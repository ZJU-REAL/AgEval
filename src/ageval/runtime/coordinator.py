"""LifecycleCoordinator — drives generic stages with cleanup-once semantics.

Stage implementations are an internal seam (``LifecycleStages``). Production
L0 and L1 both select a stages object (``LocalL0Stages`` / ``DockerL1Stages``)
and pass a minted ``attempt`` into ``run_lifecycle``. Tests inject doubles via
the application use case, never via CLI composition.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from ageval.runtime.cancellation import CancellationSignal, MonotonicClock, default_monotonic_clock
from ageval.runtime.errors import (
    ERROR_DUPLICATE_STAGE,
    ERROR_ILLEGAL_TRANSITION,
    ERROR_INVALID_ARGUMENT,
    LifecycleError,
)
from ageval.runtime.identity import AttemptIdentity, assert_same_attempt
from ageval.runtime.lifecycle import LifecyclePhase, LifecycleState, validate_transition
from ageval.runtime.outcomes import (
    AttemptRecord,
    LifecycleEvent,
    PhaseFact,
    PhaseStatus,
    RuntimeTerminalKind,
)

StageFn = Callable[[AttemptIdentity], Awaitable[PhaseFact]]


class LifecycleStages(Protocol):
    """Internal stage seam — returns identity-bound generic PhaseFact only."""

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact: ...

    async def run(self, attempt: AttemptIdentity) -> PhaseFact: ...

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact: ...

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact: ...

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact: ...

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact: ...


@dataclass
class LifecycleCoordinator:
    """Process-in-memory outer lifecycle driver for a single Attempt."""

    stages: LifecycleStages
    cancellation: CancellationSignal = field(default_factory=CancellationSignal)
    clock: MonotonicClock = field(default=default_monotonic_clock)
    cleanup_wait_budget: float = 5.0
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.cleanup_wait_budget <= 0:
            raise LifecycleError(
                ERROR_INVALID_ARGUMENT,
                "cleanup_wait_budget must be positive",
            )

    async def run(self, attempt: AttemptIdentity) -> AttemptRecord:
        """Drive the success path or early-cleanup branches for *attempt*."""
        state = LifecycleState.CREATED
        events: list[LifecycleEvent] = []
        facts: list[PhaseFact] = []
        seq = 0
        cleanup_calls = 0
        cleanup_started = False
        cleanup_warning: str | None = None
        primary_terminal: RuntimeTerminalKind | None = None
        completed_phases: set[LifecyclePhase] = set()

        def transition(target: LifecycleState, reason: str) -> None:
            nonlocal state, seq
            # Map coordinator reason → validate_transition reason.
            if reason == "success":
                vt_reason = "success"
            elif reason == "cleanup_done":
                vt_reason = "cleanup_done"
            else:
                # failure / cancelled / timed_out → early cleaning_up
                vt_reason = reason if reason in {"failure", "cancelled", "timed_out"} else "failure"
            validate_transition(state, target, reason=vt_reason)
            events.append(
                LifecycleEvent(
                    attempt=attempt,
                    sequence=seq,
                    from_state=state,
                    to_state=target,
                    reason=reason,
                )
            )
            seq += 1
            state = target

        def check_abort() -> str | None:
            if self.cancellation.is_cancelled:
                return "cancelled"
            if self.deadline_monotonic is not None and self.clock() >= self.deadline_monotonic:
                return "timed_out"
            return None

        async def do_cleanup(primary: RuntimeTerminalKind) -> None:
            nonlocal cleanup_calls, cleanup_started, cleanup_warning, primary_terminal
            if cleanup_started:
                return
            cleanup_started = True
            primary_terminal = primary

            if state != LifecycleState.CLEANING_UP:
                if primary == RuntimeTerminalKind.SUCCEEDED:
                    transition(LifecycleState.CLEANING_UP, "success")
                elif primary == RuntimeTerminalKind.CANCELLED:
                    transition(LifecycleState.CLEANING_UP, "cancelled")
                elif primary == RuntimeTerminalKind.TIMED_OUT:
                    transition(LifecycleState.CLEANING_UP, "timed_out")
                else:
                    transition(LifecycleState.CLEANING_UP, "failure")

            cleanup_calls += 1
            t0 = self.clock()
            try:
                fact = await asyncio.wait_for(
                    self.stages.cleanup(attempt),
                    timeout=self.cleanup_wait_budget,
                )
                assert_same_attempt(attempt, fact.attempt)
                if fact.phase != LifecyclePhase.CLEANUP:
                    raise LifecycleError(
                        ERROR_ILLEGAL_TRANSITION,
                        f"cleanup returned wrong phase: {fact.phase.value}",
                    )
                duration_ms = max(0.0, (self.clock() - t0) * 1000.0)
                if fact.duration_ms is None:
                    fact = PhaseFact(
                        attempt=fact.attempt,
                        phase=fact.phase,
                        status=fact.status,
                        message=fact.message,
                        detail=dict(fact.detail),
                        duration_ms=duration_ms,
                    )
                facts.append(fact)
                if fact.status != PhaseStatus.SUCCEEDED:
                    cleanup_warning = fact.message or f"cleanup {fact.status.value}"
            except TimeoutError:
                cleanup_warning = "cleanup timed_out within wait budget"
                facts.append(
                    PhaseFact(
                        attempt=attempt,
                        phase=LifecyclePhase.CLEANUP,
                        status=PhaseStatus.TIMED_OUT,
                        message=cleanup_warning,
                        duration_ms=max(0.0, (self.clock() - t0) * 1000.0),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — capture as warning, keep primary
                cleanup_warning = f"cleanup failed: {type(exc).__name__}"
                facts.append(
                    PhaseFact(
                        attempt=attempt,
                        phase=LifecyclePhase.CLEANUP,
                        status=PhaseStatus.FAILED,
                        message=cleanup_warning,
                        duration_ms=max(0.0, (self.clock() - t0) * 1000.0),
                    )
                )

            transition(LifecycleState.TERMINAL, "cleanup_done")

        # Ordered outer stages after created.
        ordered: list[tuple[str, LifecycleState, LifecyclePhase | None, StageFn | None]] = [
            ("stage", LifecycleState.PREPARING, LifecyclePhase.PREPARE, self.stages.prepare),
            ("stage", LifecycleState.RUNNING_HARNESS, LifecyclePhase.RUN, self.stages.run),
            ("boundary", LifecycleState.HARNESS_TERMINAL, None, None),
            ("stage", LifecycleState.SEALING_INPUTS, LifecyclePhase.SEAL, self.stages.seal),
            ("stage", LifecycleState.EVALUATING, LifecyclePhase.EVALUATE, self.stages.evaluate),
            ("stage", LifecycleState.BINDING_RESULT, LifecyclePhase.BIND, self.stages.bind),
        ]

        finished_early = False
        for kind, target_state, phase, fn in ordered:
            abort = check_abort()
            if abort is not None:
                terminal = (
                    RuntimeTerminalKind.CANCELLED
                    if abort == "cancelled"
                    else RuntimeTerminalKind.TIMED_OUT
                )
                if phase is not None:
                    facts.append(
                        PhaseFact(
                            attempt=attempt,
                            phase=phase,
                            status=(
                                PhaseStatus.CANCELLED
                                if abort == "cancelled"
                                else PhaseStatus.TIMED_OUT
                            ),
                            message=abort,
                        )
                    )
                await do_cleanup(terminal)
                finished_early = True
                break

            transition(target_state, "success")

            if kind == "boundary" or fn is None or phase is None:
                continue

            if phase in completed_phases:
                raise LifecycleError(
                    ERROR_DUPLICATE_STAGE,
                    f"duplicate stage: {phase.value}",
                )

            t0 = self.clock()
            try:
                fact = await fn(attempt)
            except Exception as exc:  # noqa: BLE001 — stage failure → cleanup
                facts.append(
                    PhaseFact(
                        attempt=attempt,
                        phase=phase,
                        status=PhaseStatus.FAILED,
                        message=f"{type(exc).__name__}: {exc}",
                        duration_ms=max(0.0, (self.clock() - t0) * 1000.0),
                    )
                )
                await do_cleanup(RuntimeTerminalKind.FAILED)
                finished_early = True
                break

            assert_same_attempt(attempt, fact.attempt)
            if fact.phase != phase:
                raise LifecycleError(
                    ERROR_ILLEGAL_TRANSITION,
                    f"stage returned wrong phase: {fact.phase.value} != {phase.value}",
                )
            duration_ms = max(0.0, (self.clock() - t0) * 1000.0)
            if fact.duration_ms is None:
                fact = PhaseFact(
                    attempt=fact.attempt,
                    phase=fact.phase,
                    status=fact.status,
                    message=fact.message,
                    detail=dict(fact.detail),
                    duration_ms=duration_ms,
                )
            facts.append(fact)
            completed_phases.add(phase)

            if fact.status == PhaseStatus.SUCCEEDED:
                continue
            if fact.status == PhaseStatus.CANCELLED:
                await do_cleanup(RuntimeTerminalKind.CANCELLED)
                finished_early = True
                break
            if fact.status == PhaseStatus.TIMED_OUT:
                await do_cleanup(RuntimeTerminalKind.TIMED_OUT)
                finished_early = True
                break
            await do_cleanup(RuntimeTerminalKind.FAILED)
            finished_early = True
            break

        if not finished_early:
            await do_cleanup(RuntimeTerminalKind.SUCCEEDED)

        assert primary_terminal is not None
        return AttemptRecord(
            attempt=attempt,
            state=state,
            terminal=primary_terminal,
            events=tuple(events),
            phase_facts=tuple(facts),
            cleanup_calls=cleanup_calls,
            cleanup_warning=cleanup_warning,
        )
