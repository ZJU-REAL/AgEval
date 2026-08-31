"""run_attempt still seals layer C after evaluate ERROR."""

from __future__ import annotations

from typing import Any

import pytest

from ageval.attempt import run_attempt
from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.phases import cleanup, environment, evaluate, record, run
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.defaults import register_defaults
from ageval.plugins.protocol import BindingIntent
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.services import ServiceTable
from ageval.runtime.cancellation import CancellationSignal


def _ctx(tmp_path: Any) -> AttemptCtx:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="a", run_id="r")
    registry = ExtensionRegistry()
    register_defaults(registry)
    graph = resolve(BindingIntent(profile_id="solver"), registry)
    return AttemptCtx(
        run_id="r",
        trial_id="t",
        attempt_id="a",
        lock=None,  # type: ignore[arg-type]
        profile_id="solver",
        bindings=graph,
        registry=registry,
        services=ServiceTable(),
        host=object(),  # type: ignore[arg-type]
        evidence=store,
        cancellation=CancellationSignal(),
        task_root=tmp_path,
        dataset_root=tmp_path,
    )


def _patch_phases(monkeypatch: pytest.MonkeyPatch, order: list[str], *, fail: str | None) -> None:
    async def _phase(name: str, ctx: AttemptCtx) -> None:
        ctx.phase = name
        order.append(name)
        if name == fail:
            raise RuntimeError(f"{name}_boom")

    monkeypatch.setattr(environment, "run", lambda ctx: _phase("environment", ctx))
    monkeypatch.setattr(run, "run", lambda ctx: _phase("run", ctx))
    monkeypatch.setattr(evaluate, "run", lambda ctx: _phase("evaluate", ctx))
    monkeypatch.setattr(record, "run", lambda ctx: _phase("record", ctx))
    monkeypatch.setattr(cleanup, "run", lambda ctx: _phase("cleanup", ctx))


@pytest.mark.asyncio
async def test_evaluate_error_still_records_then_cleanup(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _patch_phases(monkeypatch, order, fail="evaluate")
    ctx = _ctx(tmp_path)
    await run_attempt(ctx)
    assert order == ["environment", "run", "evaluate", "record", "cleanup"]
    failed = [f for f in ctx.phase_facts if f.name == "phase_failed"]
    assert len(failed) == 1
    assert failed[0].detail["phase"] == "evaluate"


@pytest.mark.asyncio
async def test_run_error_skips_evaluate_but_still_records(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _patch_phases(monkeypatch, order, fail="run")
    ctx = _ctx(tmp_path)
    await run_attempt(ctx)
    assert order == ["environment", "run", "record", "cleanup"]
    failed = [f for f in ctx.phase_facts if f.name == "phase_failed"]
    assert failed[0].detail["phase"] == "run"


@pytest.mark.asyncio
async def test_environment_error_skips_record(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _patch_phases(monkeypatch, order, fail="environment")
    ctx = _ctx(tmp_path)
    await run_attempt(ctx)
    assert order == ["environment", "cleanup"]
    failed = [f for f in ctx.phase_facts if f.name == "phase_failed"]
    assert failed[0].detail["phase"] == "environment"


@pytest.mark.asyncio
async def test_record_failure_after_evaluate_error_does_not_replace_phase(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []

    async def boom_evaluate(ctx: AttemptCtx) -> None:
        ctx.phase = "evaluate"
        order.append("evaluate")
        raise RuntimeError("eval_boom")

    async def boom_record(ctx: AttemptCtx) -> None:
        ctx.phase = "record"
        order.append("record")
        raise RuntimeError("record_boom")

    async def ok(name: str, ctx: AttemptCtx) -> None:
        ctx.phase = name
        order.append(name)

    monkeypatch.setattr(environment, "run", lambda ctx: ok("environment", ctx))
    monkeypatch.setattr(run, "run", lambda ctx: ok("run", ctx))
    monkeypatch.setattr(evaluate, "run", boom_evaluate)
    monkeypatch.setattr(record, "run", boom_record)
    monkeypatch.setattr(cleanup, "run", lambda ctx: ok("cleanup", ctx))
    ctx = _ctx(tmp_path)
    await run_attempt(ctx)
    assert order == ["environment", "run", "evaluate", "record", "cleanup"]
    failed = [f for f in ctx.phase_facts if f.name == "phase_failed"]
    assert failed[0].detail["phase"] == "evaluate"
    warnings = [f for f in ctx.phase_facts if f.name == "record_warning"]
    assert warnings


@pytest.mark.asyncio
async def test_on_phase_observer_sees_started_and_finished(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _patch_phases(monkeypatch, order, fail=None)
    ctx = _ctx(tmp_path)
    events: list[tuple[str, str]] = []
    ctx.on_phase = lambda event, phase: events.append((event, phase))
    await run_attempt(ctx)
    assert events == [
        ("started", "environment"),
        ("finished", "environment"),
        ("started", "run"),
        ("finished", "run"),
        ("started", "evaluate"),
        ("finished", "evaluate"),
        ("started", "record"),
        ("finished", "record"),
        ("started", "cleanup"),
        ("finished", "cleanup"),
    ]


@pytest.mark.asyncio
async def test_on_phase_observer_on_phase_failure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _patch_phases(monkeypatch, order, fail="run")
    ctx = _ctx(tmp_path)
    events: list[tuple[str, str]] = []
    ctx.on_phase = lambda event, phase: events.append((event, phase))
    await run_attempt(ctx)
    assert ("started", "run") in events
    # The failing phase still reports finished; evaluate never starts.
    assert ("finished", "run") in events
    assert all(phase != "evaluate" for _, phase in events)
    assert ("started", "record") in events
    assert ("started", "cleanup") in events
