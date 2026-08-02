"""PhaseFact / AttemptRecord immutability tests."""

from __future__ import annotations

import pytest

from bora.runtime.identity import IdentityFactory
from bora.runtime.lifecycle import LifecyclePhase
from bora.runtime.outcomes import PhaseFact, PhaseStatus


def test_phase_fact_detail_frozen() -> None:
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "e" * 64)
    attempt = factory.new_attempt(trial)
    fact = PhaseFact(
        attempt=attempt,
        phase=LifecyclePhase.PREPARE,
        status=PhaseStatus.SUCCEEDED,
        detail={"k": 1},
    )
    with pytest.raises(TypeError):
        fact.detail["k"] = 2  # type: ignore[index]
