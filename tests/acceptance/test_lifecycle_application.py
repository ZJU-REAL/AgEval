"""Application lifecycle checkpoint acceptance tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from bora.adapters.package_fs import LocalPackageReader
from bora.application.run_lifecycle import assert_retryable, run_lifecycle
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore
from bora.runtime.cancellation import CancellationSignal
from bora.runtime.errors import LifecycleError
from bora.runtime.identity import IdentityFactory
from bora.runtime.lifecycle import LifecyclePhase, LifecycleState, success_path, validate_transition
from bora.runtime.outcomes import PhaseStatus, RuntimeTerminalKind

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "config-minimal"


def _lock():
    core = ConfigCore(package_reader=LocalPackageReader())
    catalog = DeclarationCapabilityCatalog()
    return core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)


@pytest.mark.asyncio
async def test_success_trace() -> None:
    lock = _lock()
    stages = ScriptedLifecycleStages()
    record = await run_lifecycle(lock, stages)
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.state == LifecycleState.TERMINAL
    assert record.cleanup_calls == 1
    assert record.attempt.trial.locked_config_digest == lock.digest
    to_states = [e.to_state for e in record.events]
    assert to_states == list(success_path()[1:])
    assert stages.cleanup_calls == 1
    # No PASS / score in facts
    blob = str(record)
    assert "PASS" not in blob
    assert "score" not in blob.lower() or "score" not in str(record.phase_facts)


@pytest.mark.asyncio
async def test_illegal_transition() -> None:
    with pytest.raises(LifecycleError) as ei:
        validate_transition(LifecycleState.CREATED, LifecycleState.EVALUATING, reason="success")
    assert ei.value.error_code == "illegal_transition"


@pytest.mark.asyncio
async def test_cross_attempt() -> None:
    lock = _lock()
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    foreign = factory.new_attempt(trial)
    stages = ScriptedLifecycleStages(
        wrong_identity_at=LifecyclePhase.PREPARE,
        foreign_attempt=foreign,
    )
    # The coordinator will create a different attempt; prepare returns foreign.
    with pytest.raises(LifecycleError) as ei:
        await run_lifecycle(lock, stages, identity_factory=factory)
    assert ei.value.error_code == "cross_attempt"


@pytest.mark.asyncio
async def test_stage_failure() -> None:
    lock = _lock()
    stages = ScriptedLifecycleStages(fail_at=LifecyclePhase.SEAL)
    record = await run_lifecycle(lock, stages)
    assert record.terminal == RuntimeTerminalKind.FAILED
    assert record.cleanup_calls == 1
    failed = [f for f in record.phase_facts if f.phase == LifecyclePhase.SEAL]
    assert failed and failed[0].status == PhaseStatus.FAILED
    assert "evaluate" not in stages.calls


@pytest.mark.asyncio
async def test_cancel() -> None:
    lock = _lock()
    cancel = CancellationSignal()
    cancel.cancel("test")
    record = await run_lifecycle(lock, ScriptedLifecycleStages(), cancellation=cancel)
    assert record.terminal == RuntimeTerminalKind.CANCELLED
    assert record.cleanup_calls == 1


@pytest.mark.asyncio
async def test_timeout() -> None:
    lock = _lock()
    record = await run_lifecycle(
        lock,
        ScriptedLifecycleStages(),
        clock=lambda: 10.0,
        deadline_monotonic=1.0,
    )
    assert record.terminal == RuntimeTerminalKind.TIMED_OUT
    assert record.cleanup_calls == 1


@pytest.mark.asyncio
async def test_cleanup_warning() -> None:
    lock = _lock()
    stages = ScriptedLifecycleStages(cleanup_raises=True)
    record = await run_lifecycle(lock, stages)
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.cleanup_warning is not None


@pytest.mark.asyncio
async def test_retry_identity() -> None:
    lock = _lock()
    factory = IdentityFactory()
    stages = ScriptedLifecycleStages(fail_at=LifecyclePhase.RUN)
    first = await run_lifecycle(lock, stages, identity_factory=factory)
    assert first.terminal == RuntimeTerminalKind.FAILED
    assert_retryable(first)
    second = await run_lifecycle(
        lock,
        ScriptedLifecycleStages(),
        identity_factory=factory,
        retry_of=first.attempt,
        previous_record=first,
    )
    assert second.attempt.value != first.attempt.value
    assert second.attempt.retry_of_attempt_id == first.attempt.value
    assert second.attempt.trial == first.attempt.trial
    # First record unchanged (immutable).
    assert first.terminal == RuntimeTerminalKind.FAILED
    assert second.terminal == RuntimeTerminalKind.SUCCEEDED
