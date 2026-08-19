"""Cancel / timeout coordinator tests."""

from __future__ import annotations

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from ageval.runtime.cancellation import CancellationSignal
from ageval.runtime.coordinator import LifecycleCoordinator
from ageval.runtime.identity import IdentityFactory
from ageval.runtime.lifecycle import LifecyclePhase
from ageval.runtime.outcomes import RuntimeTerminalKind


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "1" * 64)
    return f.new_attempt(trial)


@pytest.mark.asyncio
async def test_cancel_before_run() -> None:
    stages = ScriptedLifecycleStages()
    cancel = CancellationSignal()
    cancel.cancel()
    record = await LifecycleCoordinator(stages=stages, cancellation=cancel).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.CANCELLED
    assert record.cleanup_calls == 1


@pytest.mark.asyncio
async def test_timeout_deadline() -> None:
    stages = ScriptedLifecycleStages()
    # Deadline already in the past relative to clock.
    record = await LifecycleCoordinator(
        stages=stages,
        clock=lambda: 100.0,
        deadline_monotonic=50.0,
    ).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.TIMED_OUT
    assert record.cleanup_calls == 1


@pytest.mark.asyncio
async def test_stage_returns_cancelled() -> None:
    from ageval.runtime.outcomes import PhaseStatus

    stages = ScriptedLifecycleStages(
        fail_at=LifecyclePhase.RUN,
        fail_status=PhaseStatus.CANCELLED,
        fail_message="cooperative cancel",
    )
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.CANCELLED
