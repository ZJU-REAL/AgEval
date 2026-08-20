"""A failed task worker is a run-phase ERROR, not a judged evaluate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ageval.attempt.phases import run as run_phase


@pytest.mark.asyncio
async def test_run_phase_raises_when_worker_envelope_is_not_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_emit(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_harvest(_ctx: object) -> None:
        return None

    async def fake_worker(_ctx: object) -> dict[str, object]:
        return {"ok": False, "error": "task_run_timeout"}

    monkeypatch.setattr(run_phase, "emit", fake_emit)
    monkeypatch.setattr(run_phase, "harvest_workspace_artifacts", fake_harvest)
    monkeypatch.setattr(run_phase, "_run_task_entry", fake_worker)

    ctx = SimpleNamespace(
        phase="",
        agent_service=None,
        assert_deadline=lambda: None,
        record_fact=lambda *_a, **_k: None,
        mark_writers_stopped=lambda: None,
    )
    with pytest.raises(RuntimeError, match="task_run_timeout"):
        await run_phase.run(ctx)  # type: ignore[arg-type]
