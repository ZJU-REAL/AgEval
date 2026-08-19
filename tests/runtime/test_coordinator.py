"""Coordinator success / failure path tests."""

from __future__ import annotations

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from ageval.runtime.coordinator import LifecycleCoordinator
from ageval.runtime.identity import IdentityFactory
from ageval.runtime.lifecycle import LifecyclePhase, LifecycleState, success_path
from ageval.runtime.outcomes import PhaseStatus, RuntimeTerminalKind


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "f" * 64)
    return f.new_attempt(trial)


@pytest.mark.asyncio
async def test_success_trace() -> None:
    stages = ScriptedLifecycleStages()
    coord = LifecycleCoordinator(stages=stages)
    record = await coord.run(_attempt())
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.state == LifecycleState.TERMINAL
    assert record.cleanup_calls == 1
    states = [e.to_state for e in record.events]
    assert states == list(success_path()[1:])  # events start after created
    phases = [f.phase for f in record.phase_facts if f.phase != LifecyclePhase.CLEANUP]
    assert phases == [
        LifecyclePhase.PREPARE,
        LifecyclePhase.RUN,
        LifecyclePhase.SEAL,
        LifecyclePhase.EVALUATE,
        LifecyclePhase.BIND,
    ]
    assert stages.cleanup_calls == 1


@pytest.mark.asyncio
async def test_prepare_failure() -> None:
    stages = ScriptedLifecycleStages(fail_at=LifecyclePhase.PREPARE)
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.FAILED
    assert record.cleanup_calls == 1
    failed = [f for f in record.phase_facts if f.phase == LifecyclePhase.PREPARE]
    assert failed and failed[0].status == PhaseStatus.FAILED
    # run must not have been called
    assert "run" not in stages.calls


@pytest.mark.asyncio
async def test_cleanup_raises_warning() -> None:
    stages = ScriptedLifecycleStages(cleanup_raises=True)
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.cleanup_warning is not None
    assert "cleanup failed" in record.cleanup_warning
