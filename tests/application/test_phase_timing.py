"""Phase timing is built from the Attempt's own ``phase_finished`` facts."""

from __future__ import annotations

from ageval.application.phase_timing import (
    TIMING_SCHEMA,
    format_duration_ms,
    timing_from_facts,
)


def _fact(phase: str, duration_ms: float) -> dict[str, object]:
    return {
        "phase": phase,
        "name": "phase_finished",
        "detail": {"phase": phase, "duration_ms": duration_ms},
    }


def test_phases_come_back_in_pipeline_order() -> None:
    timing = timing_from_facts(
        [
            _fact("cleanup", 5.0),
            _fact("run", 200.0),
            _fact("environment", 50.0),
        ]
    )
    assert timing["schema"] == TIMING_SCHEMA
    assert [p["id"] for p in timing["phases"]] == ["environment", "run", "cleanup"]
    assert timing["total_ms"] == 255.0


def test_repeated_phase_accumulates() -> None:
    timing = timing_from_facts([_fact("run", 10.0), _fact("run", 15.5)])
    assert timing["phases"] == [
        {"id": "run", "label": "Agent Execution", "duration_ms": 25.5},
    ]


def test_unrelated_facts_and_bad_durations_are_ignored() -> None:
    timing = timing_from_facts(
        [
            {"phase": "run", "name": "task_run", "detail": {"duration_ms": 999.0}},
            {"phase": "run", "name": "phase_finished", "detail": {"phase": "run"}},
            {"phase": "run", "name": "phase_finished"},
        ]
    )
    assert timing["phases"] == []
    assert timing["total_ms"] == 0.0


def test_duration_labels_read_like_a_clock() -> None:
    assert format_duration_ms(None) is None
    assert format_duration_ms(830) == "830ms"
    assert format_duration_ms(4500) == "4.5s"
    assert format_duration_ms(72000) == "1m 12s"
    assert format_duration_ms(120000) == "2m"


def test_wall_clock_comes_from_phase_finished_facts() -> None:
    timing = timing_from_facts(
        [
            {
                "phase": "environment",
                "name": "phase_finished",
                "detail": {
                    "phase": "environment",
                    "duration_ms": 50.0,
                    "started_at": "2026-08-20T10:00:00Z",
                    "finished_at": "2026-08-20T10:00:01Z",
                },
            },
            {
                "phase": "run",
                "name": "phase_finished",
                "detail": {
                    "phase": "run",
                    "duration_ms": 200.0,
                    "started_at": "2026-08-20T10:00:01Z",
                    "finished_at": "2026-08-20T10:00:03Z",
                },
            },
        ]
    )
    assert timing["started_at"] == "2026-08-20T10:00:00Z"
    assert timing["finished_at"] == "2026-08-20T10:00:03Z"
