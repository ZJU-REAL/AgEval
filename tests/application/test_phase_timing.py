"""Phase timing helpers + coordinator duration_ms (#47 D)."""

from __future__ import annotations

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from bora.application.attempt.phase_timing import (
    PhaseTimer,
    bucket_phase_timing,
    format_duration_ms,
    phase_facts_to_timing,
)
from bora.runtime.coordinator import LifecycleCoordinator
from bora.runtime.identity import IdentityFactory
from bora.runtime.outcomes import RuntimeTerminalKind


def test_phase_timer_as_dict() -> None:
    t = PhaseTimer()
    with t.phase("prepare"):
        pass
    t.add_ms("run", 1500.0)
    t.add_ms("evaluate", 250.0)
    doc = t.as_dict()
    assert doc["schema"] == "bora.phase_timing/1"
    ids = [p["id"] for p in doc["phases"]]
    assert "prepare" in ids
    assert "run" in ids
    assert doc["total_ms"] >= 1500.0
    assert any(p["label"] == "Agent Execution" for p in doc["phases"] if p["id"] == "run")


def test_format_duration() -> None:
    assert format_duration_ms(500) == "500ms"
    assert format_duration_ms(12_000) == "12s"
    assert format_duration_ms(72_000) == "1m 12s"


def test_bucket_merges_seal_bind_into_evaluate() -> None:
    doc = bucket_phase_timing(
        [
            {"id": "prepare", "duration_ms": 100},
            {"id": "run", "duration_ms": 1000},
            {"id": "seal", "duration_ms": 50},
            {"id": "evaluate", "duration_ms": 200},
            {"id": "bind", "duration_ms": 30},
            {"id": "cleanup", "duration_ms": 40},
        ]
    )
    by_id = {p["id"]: p["duration_ms"] for p in doc["phases"]}
    assert by_id["evaluate"] == pytest.approx(280.0)
    assert "seal" not in by_id


@pytest.mark.asyncio
async def test_coordinator_records_duration_ms() -> None:
    stages = ScriptedLifecycleStages()
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "a" * 64)
    attempt = f.new_attempt(trial)
    record = await LifecycleCoordinator(stages=stages).run(attempt)
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.phase_facts
    assert all(f.duration_ms is not None and f.duration_ms >= 0 for f in record.phase_facts)
    timing = phase_facts_to_timing(record.phase_facts)
    assert timing["total_ms"] >= 0
    assert any(p["id"] == "run" for p in timing["phases"])
