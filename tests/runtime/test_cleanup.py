"""Cleanup-once and cleanup timeout tests."""

from __future__ import annotations

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from bora.runtime.coordinator import LifecycleCoordinator
from bora.runtime.identity import IdentityFactory
from bora.runtime.lifecycle import LifecyclePhase
from bora.runtime.outcomes import PhaseStatus, RuntimeTerminalKind


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "2" * 64)
    return f.new_attempt(trial)


@pytest.mark.asyncio
async def test_cleanup_timeout_warning() -> None:
    stages = ScriptedLifecycleStages(hang_at=LifecyclePhase.CLEANUP, hang_seconds=10.0)
    record = await LifecycleCoordinator(stages=stages, cleanup_wait_budget=0.05).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.cleanup_warning is not None
    assert "timed_out" in record.cleanup_warning
    assert any(f.status == PhaseStatus.TIMED_OUT for f in record.phase_facts)


@pytest.mark.asyncio
async def test_cleanup_once_on_failure() -> None:
    stages = ScriptedLifecycleStages(fail_at=LifecyclePhase.EVALUATE)
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.cleanup_calls == 1
    assert stages.cleanup_calls == 1
