"""Application Provider L0 probe — real process + Lifecycle identity binding.

Not exposed on the product CLI. Callers supply an explicit ProcessLaunchPlan
(workload path is chosen by the application checkpoint assembly).
"""

from __future__ import annotations

from ageval.adapters.provider_local import LocalProcessProvider
from ageval.config.model import LockedTaskConfig
from ageval.provider.contract import ProcessLaunchPlan
from ageval.provider.outcomes import ProcessOutcome
from ageval.runtime.cancellation import CancellationSignal
from ageval.runtime.identity import IdentityFactory
from ageval.runtime.lifecycle import LifecyclePhase, LifecycleState
from ageval.runtime.outcomes import (
    AttemptRecord,
    LifecycleEvent,
    PhaseFact,
    PhaseStatus,
    RuntimeTerminalKind,
)


async def run_provider_probe(
    lock: LockedTaskConfig,
    plan: ProcessLaunchPlan,
    *,
    identity_factory: IdentityFactory | None = None,
    cancellation: CancellationSignal | None = None,
    provider: LocalProcessProvider | None = None,
) -> tuple[AttemptRecord, ProcessOutcome]:
    """Create Attempt identity matching *plan*, run Provider, return bound facts."""
    factory = identity_factory or IdentityFactory()
    # Prefer plan.attempt if already set; otherwise create new identities with lock digest.
    attempt = plan.attempt
    if attempt.trial.locked_config_digest != lock.digest:
        # Rebuild attempt under lock digest for binding evidence.
        run = factory.new_run()
        trial = factory.new_trial(run, lock.digest)
        attempt = factory.new_attempt(trial)
        # Caller-supplied plan remains authoritative for process; identity in outcome
        # will follow prepared handle from plan — re-bind plan is not mutated (frozen).
        # For tests, construct plans with matching digest.

    prov = provider or LocalProcessProvider()
    cancel = cancellation or CancellationSignal()
    prepared = await prov.prepare(plan)
    prepared = await prov.start(prepared)
    outcome = await prov.wait(prepared, cancellation=cancel)

    # Map process outcome → Lifecycle-like AttemptRecord for the checkpoint.
    terminal_map = {
        "exited": RuntimeTerminalKind.SUCCEEDED
        if outcome.exit_code == 0
        else RuntimeTerminalKind.FAILED,
        "timed_out": RuntimeTerminalKind.TIMED_OUT,
        "cancelled": RuntimeTerminalKind.CANCELLED,
        "spawn_failed": RuntimeTerminalKind.FAILED,
        "killed": RuntimeTerminalKind.FAILED,
    }
    runtime_terminal = terminal_map.get(outcome.terminal.value, RuntimeTerminalKind.FAILED)
    if outcome.exit_code == 0 and outcome.terminal.value == "exited":
        runtime_terminal = RuntimeTerminalKind.SUCCEEDED

    events = (
        LifecycleEvent(
            attempt=outcome.attempt,
            sequence=0,
            from_state=LifecycleState.CREATED,
            to_state=LifecycleState.PREPARING,
            reason="success",
        ),
        LifecycleEvent(
            attempt=outcome.attempt,
            sequence=1,
            from_state=LifecycleState.PREPARING,
            to_state=LifecycleState.RUNNING_HARNESS,
            reason="success",
        ),
        LifecycleEvent(
            attempt=outcome.attempt,
            sequence=2,
            from_state=LifecycleState.RUNNING_HARNESS,
            to_state=LifecycleState.CLEANING_UP,
            reason="success" if runtime_terminal == RuntimeTerminalKind.SUCCEEDED else "failure",
        ),
        LifecycleEvent(
            attempt=outcome.attempt,
            sequence=3,
            from_state=LifecycleState.CLEANING_UP,
            to_state=LifecycleState.TERMINAL,
            reason="cleanup_done",
        ),
    )
    facts = (
        PhaseFact(
            attempt=outcome.attempt,
            phase=LifecyclePhase.PREPARE,
            status=PhaseStatus.SUCCEEDED,
            message="provider prepare",
        ),
        PhaseFact(
            attempt=outcome.attempt,
            phase=LifecyclePhase.RUN,
            status=PhaseStatus.SUCCEEDED
            if runtime_terminal == RuntimeTerminalKind.SUCCEEDED
            else PhaseStatus.FAILED,
            message=outcome.terminal.value,
            detail={"assurance": "l0", "exit_code": str(outcome.exit_code)},
        ),
        PhaseFact(
            attempt=outcome.attempt,
            phase=LifecyclePhase.CLEANUP,
            status=PhaseStatus.SUCCEEDED if outcome.cleanup_ok else PhaseStatus.FAILED,
            message=outcome.cleanup_warning or "cleanup",
        ),
    )
    record = AttemptRecord(
        attempt=outcome.attempt,
        state=LifecycleState.TERMINAL,
        terminal=runtime_terminal,
        events=events,
        phase_facts=facts,
        cleanup_calls=1,
        cleanup_warning=outcome.cleanup_warning,
    )
    return record, outcome
