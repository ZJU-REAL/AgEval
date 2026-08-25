"""Evaluate/record phases bind exclusive winners; PASS still only via bind_evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.phases import evaluate, record
from ageval.environments.protocol import EVALUATION_PATH
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.defaults import register_defaults
from ageval.plugins.protocol import BindingIntent, ExplicitBinding, HandlerRef
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.services import ServiceTable
from ageval.plugins.slots import (
    AFTER_EVALUATE,
    EVALUATION_RUNTIME,
    TRAJECTORY_COLLECT,
    TRAJECTORY_SEAL,
)
from ageval.runtime.cancellation import CancellationSignal


class RecordingHost:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []

    async def upload(self, source: Path, dest: str) -> None:
        self.uploads.append((Path(source), str(dest)))


class RawPassRuntime:
    async def evaluate(self, ctx: Any) -> dict[str, Any]:
        del ctx
        return {"status": "PASS", "score": 1}


class ProbeSeal:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    def seal(self, ctx: Any, turns: list[list[dict[str, Any]]]) -> Path:
        self.order.append("seal")
        path = ctx.evidence.root / "trajectory.jsonl"
        path.write_text(f'{{"turns": {len(turns)}, "probe": true}}\n', encoding="utf-8")
        return path


def _registry_with_runtime() -> ExtensionRegistry:
    registry = ExtensionRegistry()
    register_defaults(registry)
    registry.exclusive(
        EVALUATION_RUNTIME,
        "probe",
        lambda **_kwargs: RawPassRuntime(),
        source="test",
        is_factory=True,
    )
    return registry


def _ctx(
    tmp_path: Path,
    *,
    registry: ExtensionRegistry,
    graph: Any,
    host: Any | None = None,
    evaluation_src: Path | None = None,
) -> AttemptCtx:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="a", run_id="r")
    ctx = AttemptCtx(
        run_id="r",
        trial_id="t",
        attempt_id="a",
        lock=None,  # type: ignore[arg-type]
        profile_id="solver",
        bindings=graph,
        registry=registry,
        services=ServiceTable(),
        host=host or RecordingHost(),  # type: ignore[arg-type]
        evidence=store,
        cancellation=CancellationSignal(),
        task_root=tmp_path,
        dataset_root=tmp_path,
        evaluation_src=evaluation_src,
    )
    ctx.mark_writers_stopped()
    return ctx


@pytest.mark.asyncio
async def test_runtime_return_is_not_a_bound_pass(tmp_path: Path) -> None:
    registry = _registry_with_runtime()
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extensions=[ExplicitBinding(slot=EVALUATION_RUNTIME, plugin="probe")],
        ),
        registry,
    )
    ctx = _ctx(tmp_path, registry=registry, graph=graph)
    ctx.phase = "evaluate"
    raw = await RawPassRuntime().evaluate(ctx)
    assert raw["status"] == "PASS"
    assert ctx.evaluation_result is None


@pytest.mark.asyncio
async def test_evaluate_phase_binds_winner_raw_and_uploads_gold(tmp_path: Path) -> None:
    gold = tmp_path / "evaluation"
    gold.mkdir()
    (gold / "expected.txt").write_text("ok\n", encoding="utf-8")
    registry = _registry_with_runtime()
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extensions=[ExplicitBinding(slot=EVALUATION_RUNTIME, plugin="probe")],
        ),
        registry,
    )
    host = RecordingHost()
    ctx = _ctx(tmp_path, registry=registry, graph=graph, host=host, evaluation_src=gold)
    await evaluate.run(ctx)
    assert ctx.evaluation_result == {"status": "PASS", "score": 1}
    assert ctx.services.owner(EVALUATION_RUNTIME) == "probe"
    assert any(dest == EVALUATION_PATH for _src, dest in host.uploads)
    assert any(f.name == "gold_materialized" and f.phase == "evaluate" for f in ctx.phase_facts)


@pytest.mark.asyncio
async def test_after_evaluate_cannot_change_status(tmp_path: Path) -> None:
    async def flip_status(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        out = await nxt(value)
        return {**out, "status": "FAIL"}

    registry = _registry_with_runtime()
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extensions=[ExplicitBinding(slot=EVALUATION_RUNTIME, plugin="probe")],
        ),
        registry,
    )
    graph.chains[AFTER_EVALUATE] = [
        HandlerRef(plugin_id="probe", handler=flip_status, priority=1, source="test")
    ]
    ctx = _ctx(tmp_path, registry=registry, graph=graph)
    with pytest.raises(RuntimeError, match="after_evaluate must not change"):
        await evaluate.run(ctx)
    assert ctx.evaluation_result == {"status": "PASS", "score": 1}


@pytest.mark.asyncio
async def test_seal_winner_writes_after_collect(tmp_path: Path) -> None:
    order: list[str] = []

    async def collect(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        order.append("collect")
        return await nxt(value)

    registry = ExtensionRegistry()
    register_defaults(registry)
    registry.exclusive(
        TRAJECTORY_SEAL,
        "probe-seal",
        lambda **_kwargs: ProbeSeal(order),
        source="test",
        is_factory=True,
    )
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extensions=[ExplicitBinding(slot=TRAJECTORY_SEAL, plugin="probe-seal")],
        ),
        registry,
    )
    graph.chains[TRAJECTORY_COLLECT] = [
        HandlerRef(plugin_id="probe", handler=collect, priority=1, source="test")
    ]
    ctx = _ctx(tmp_path, registry=registry, graph=graph)
    inv = ctx.evidence.root / "agent" / "invocations" / "001"
    inv.mkdir(parents=True)
    (inv / "metadata.json").write_text('{"seq": 1, "status": "completed"}', encoding="utf-8")
    (inv / "final-response.json").write_text('{"content": "hi"}', encoding="utf-8")
    (inv / "request.json").write_text('{"messages": [{"content": "go"}]}', encoding="utf-8")
    (inv / "events.jsonl").write_text("", encoding="utf-8")
    await record.run(ctx)
    assert order == ["collect", "seal"]
    text = (ctx.evidence.root / "trajectory.jsonl").read_text(encoding="utf-8")
    assert '"probe": true' in text
    assert ctx.services.owner(TRAJECTORY_SEAL) == "probe-seal"


@pytest.mark.asyncio
async def test_collect_usage_extra_lands_on_terminal(tmp_path: Path) -> None:
    import json

    async def collect(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        out = await nxt(value)
        if not isinstance(out, dict):
            return out
        usage = dict(out.get("usage") or {})
        extra = dict(usage.get("extra") or {})
        extra["foo"] = True
        usage["extra"] = extra
        out["usage"] = usage
        return out

    registry = ExtensionRegistry()
    register_defaults(registry)
    graph = resolve(BindingIntent(profile_id="solver"), registry)
    graph.chains[TRAJECTORY_COLLECT] = [
        HandlerRef(plugin_id="probe", handler=collect, priority=1, source="test")
    ]
    ctx = _ctx(tmp_path, registry=registry, graph=graph)
    inv = ctx.evidence.root / "agent" / "invocations" / "001"
    inv.mkdir(parents=True)
    (inv / "metadata.json").write_text(
        '{"seq": 1, "status": "completed", "latency_ms": 88}',
        encoding="utf-8",
    )
    (inv / "final-response.json").write_text(
        '{"content": "hi", "usage": {"prompt_tokens": 3, "completion_tokens": 1}}',
        encoding="utf-8",
    )
    (inv / "request.json").write_text(
        '{"messages": [{"content": "go"}]}',
        encoding="utf-8",
    )
    (inv / "events.jsonl").write_text("", encoding="utf-8")
    await record.run(ctx)
    lines = [
        json.loads(line)
        for line in (ctx.evidence.root / "trajectory.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    terminal = next(row for row in lines if row["type"] == "terminal")
    assert terminal["usage"]["prompt_tokens"] == 3
    assert terminal["usage"]["completion_tokens"] == 1
    assert terminal["usage"]["extra"]["foo"] is True
    assert terminal["elapsed_ms"] == 88
