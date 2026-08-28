"""Isolated evaluate host: gold and snapshots stay off the agent box."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.phases import cleanup, evaluate
from ageval.environments.protocol import EVALUATION_PATH, WORKSPACE_PATH
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.defaults import register_defaults
from ageval.plugins.protocol import BindingIntent, ExplicitBinding
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.services import ServiceTable
from ageval.plugins.slots import ENVIRONMENT, EVALUATION_RUNTIME
from ageval.runtime.cancellation import CancellationSignal


class RecordingHost:
    def __init__(self, *, root: Path, kind: str = "docker") -> None:
        self.kind = kind
        self.root = root
        self.uploads: list[tuple[Path, str]] = []
        self.started = False
        self.stopped = False
        self.preflighted = False

    async def preflight(self) -> None:
        self.preflighted = True

    async def start(self, *, force_build: bool = False) -> None:
        del force_build
        self.started = True

    async def stop(self, *, delete: bool) -> None:
        del delete
        self.stopped = True

    async def upload(self, source: Path, dest: str) -> None:
        self.uploads.append((Path(source), str(dest)))


class RawPassRuntime:
    async def evaluate(self, ctx: Any) -> dict[str, Any]:
        del ctx
        return {"status": "PASS", "score": 1}


def _registry() -> ExtensionRegistry:
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
    agent: RecordingHost,
    evaluate_host: RecordingHost | None,
    lock: Any,
    evaluation_src: Path | None = None,
    evaluate_hosts: dict[str, RecordingHost] | None = None,
) -> AttemptCtx:
    registry = _registry()
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extensions=[ExplicitBinding(slot=EVALUATION_RUNTIME, plugin="probe")],
        ),
        registry,
    )
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="a", run_id="r")
    ctx = AttemptCtx(
        run_id="r",
        trial_id="t",
        attempt_id="a",
        lock=lock,
        profile_id="solver",
        bindings=graph,
        registry=registry,
        services=ServiceTable(),
        host=agent,  # type: ignore[arg-type]
        evidence=store,
        cancellation=CancellationSignal(),
        task_root=tmp_path,
        dataset_root=tmp_path,
        evaluate_host=evaluate_host,  # type: ignore[arg-type]
        evaluate_hosts=dict(evaluate_hosts or {}),  # type: ignore[arg-type]
        evaluation_src=evaluation_src,
    )
    ctx.mark_writers_stopped()
    return ctx


def _lock(*, artifacts: list[dict[str, object]] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        force_build=False,
        resolved_references={
            "artifacts": artifacts or [],
            "evaluation_inputs": [{"artifact": "repo", "target": "workspace"}] if artifacts else [],
        },
        job_overlay={"evaluate_host": {"isolated": True}},
    )


@pytest.mark.asyncio
async def test_isolated_evaluate_uploads_gold_only_to_scoring_host(tmp_path: Path) -> None:
    gold = tmp_path / "evaluation"
    gold.mkdir()
    (gold / "hidden.txt").write_text("secret\n", encoding="utf-8")
    agent = RecordingHost(root=tmp_path / "agent")
    scoring = RecordingHost(root=tmp_path / "eval")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=scoring,
        lock=_lock(),
        evaluation_src=gold,
    )
    ctx.services.register(ENVIRONMENT, agent, plugin_id="docker")
    await evaluate.run(ctx)
    assert scoring.started is True
    assert scoring.preflighted is True
    assert agent.started is False
    assert ctx.services.require(ENVIRONMENT) is scoring
    assert any(dest == EVALUATION_PATH for _src, dest in scoring.uploads)
    assert not any(dest == EVALUATION_PATH for _src, dest in agent.uploads)
    assert ctx.evaluation_result == {"status": "PASS", "score": 1}
    assert any(f.name == "evaluate_host_started" for f in ctx.phase_facts)


@pytest.mark.asyncio
async def test_isolated_tree_rematerializes_on_scoring_workspace(tmp_path: Path) -> None:
    snap = tmp_path / "run" / "task-artifacts" / "repo"
    snap.mkdir(parents=True)
    (snap / "src.py").write_text("from snapshot\n", encoding="utf-8")
    agent = RecordingHost(root=tmp_path / "agent")
    scoring = RecordingHost(root=tmp_path / "eval")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=scoring,
        lock=_lock(
            artifacts=[{"id": "repo", "path": "workspace", "kind": "tree", "exclude": ["target"]}]
        ),
    )
    await evaluate.run(ctx)
    assert any(dest == WORKSPACE_PATH for src, dest in scoring.uploads if src == snap)
    assert not any(dest == WORKSPACE_PATH for _src, dest in agent.uploads)


@pytest.mark.asyncio
async def test_cleanup_stops_both_hosts(tmp_path: Path) -> None:
    agent = RecordingHost(root=tmp_path / "agent")
    scoring = RecordingHost(root=tmp_path / "eval")
    ctx = _ctx(tmp_path, agent=agent, evaluate_host=scoring, lock=_lock())
    await cleanup.run(ctx)
    assert scoring.stopped is True
    assert agent.stopped is True
    names = [f.name for f in ctx.phase_facts]
    assert "evaluate_host_stopped" in names
    assert "environment_stopped" in names


@pytest.mark.asyncio
async def test_same_box_evaluate_does_not_start_a_second_host(tmp_path: Path) -> None:
    gold = tmp_path / "evaluation"
    gold.mkdir()
    (gold / "expected.txt").write_text("ok\n", encoding="utf-8")
    agent = RecordingHost(root=tmp_path / "agent")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        lock=SimpleNamespace(force_build=False, resolved_references={}, job_overlay={}),
        evaluation_src=gold,
    )
    await evaluate.run(ctx)
    assert agent.started is False
    assert any(dest == EVALUATION_PATH for _src, dest in agent.uploads)
    assert not any(f.name == "evaluate_host_started" for f in ctx.phase_facts)


def _named_lock() -> SimpleNamespace:
    return SimpleNamespace(
        force_build=False,
        resolved_references={
            "evaluation_environments": {
                "audit": {"dockerfile": "environment/evaluate/audit/Dockerfile"},
                "unused": {"dockerfile": "environment/evaluate/unused/Dockerfile"},
            },
            "artifacts": [
                {"id": "repo", "path": "workspace", "kind": "tree", "exclude": ["target"]}
            ],
            "evaluation_inputs": [{"artifact": "repo", "target": "workspace"}],
        },
        job_overlay={"evaluate_host": {"isolated": True}},
    )


@pytest.mark.asyncio
async def test_named_evaluate_does_not_start_hosts_until_exec(tmp_path: Path) -> None:
    gold = tmp_path / "evaluation"
    gold.mkdir()
    (gold / "hidden.txt").write_text("secret\n", encoding="utf-8")
    snap = tmp_path / "run" / "task-artifacts" / "repo"
    snap.mkdir(parents=True)
    (snap / "src.py").write_text("from snapshot\n", encoding="utf-8")
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    unused = RecordingHost(root=tmp_path / "unused")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit, "unused": unused},
        lock=_named_lock(),
        evaluation_src=gold,
    )
    await evaluate.run(ctx)
    assert audit.started is False
    assert unused.started is False
    assert not any(f.name == "evaluate_host_started" for f in ctx.phase_facts)
    assert ctx.evaluation_result == {"status": "PASS", "score": 1}


@pytest.mark.asyncio
async def test_named_ensure_starts_only_requested_host(tmp_path: Path) -> None:
    gold = tmp_path / "evaluation"
    gold.mkdir()
    (gold / "hidden.txt").write_text("secret\n", encoding="utf-8")
    snap = tmp_path / "run" / "task-artifacts" / "repo"
    snap.mkdir(parents=True)
    (snap / "src.py").write_text("from snapshot\n", encoding="utf-8")
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    unused = RecordingHost(root=tmp_path / "unused")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit, "unused": unused},
        lock=_named_lock(),
        evaluation_src=gold,
    )
    ctx.phase = "evaluate"
    host = await evaluate.ensure_named_host(ctx, "audit")
    assert host is audit
    assert audit.started is True
    assert unused.started is False
    assert any(dest == EVALUATION_PATH for _src, dest in audit.uploads)
    assert any(dest == WORKSPACE_PATH for src, dest in audit.uploads if src == snap)
    assert not any(dest == EVALUATION_PATH for _src, dest in unused.uploads)
    facts = [f for f in ctx.phase_facts if f.name == "evaluate_host_started"]
    assert len(facts) == 1
    assert facts[0].detail.get("name") == "audit"


@pytest.mark.asyncio
async def test_named_unknown_environment_does_not_start(tmp_path: Path) -> None:
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit},
        lock=_named_lock(),
    )
    ctx.phase = "evaluate"
    with pytest.raises(RuntimeError, match="unknown_evaluate_environment"):
        await evaluate.ensure_named_host(ctx, "nope")
    assert audit.started is False


@pytest.mark.asyncio
async def test_bind_named_environment_rebinds_environment_service(tmp_path: Path) -> None:
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    unused = RecordingHost(root=tmp_path / "unused")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit, "unused": unused},
        lock=_named_lock(),
    )
    ctx.services.register(ENVIRONMENT, agent, plugin_id="docker")
    ctx.phase = "evaluate"
    host = await evaluate.bind_named_environment(ctx, "audit", profile_id="judge")
    assert host is audit
    assert ctx.services.require(ENVIRONMENT) is audit
    assert unused.started is False


@pytest.mark.asyncio
async def test_bind_named_environment_prepares_only_the_opened_profile(tmp_path: Path) -> None:
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    lock = _named_lock()
    lock.agent_profiles = (
        {"id": "judge", "executor": "acp"},
        {"id": "other", "executor": "acp"},
    )
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit},
        lock=lock,
    )
    ctx.phase = "evaluate"
    prepared: list[str] = []

    class _Graph:
        def chain(self, slot: str) -> list[object]:
            del slot
            return []

    class _Binder:
        def graph(self, profile_id: str) -> _Graph:
            prepared.append(profile_id)
            return _Graph()

    ctx.agent_service = SimpleNamespace(binder=_Binder(), _run_profile_ids=set())
    await evaluate.bind_named_environment(ctx, "audit", profile_id="judge")
    assert prepared == ["judge"]
    facts = [f for f in ctx.phase_facts if f.name == "evaluate_runtime_prepared"]
    assert [f.detail.get("profile_id") for f in facts] == ["judge"]
    await evaluate.bind_named_environment(ctx, "audit", profile_id="judge")
    assert prepared == ["judge"]


@pytest.mark.asyncio
async def test_cleanup_stops_only_started_named_hosts(tmp_path: Path) -> None:
    agent = RecordingHost(root=tmp_path / "agent")
    audit = RecordingHost(root=tmp_path / "audit")
    unused = RecordingHost(root=tmp_path / "unused")
    ctx = _ctx(
        tmp_path,
        agent=agent,
        evaluate_host=None,
        evaluate_hosts={"audit": audit, "unused": unused},
        lock=_named_lock(),
    )
    ctx.phase = "evaluate"
    await evaluate.ensure_named_host(ctx, "audit")
    await cleanup.run(ctx)
    assert audit.stopped is True
    assert unused.stopped is False
    names = [f.name for f in ctx.phase_facts]
    assert "evaluate_host_stopped" in names
    assert "environment_stopped" in names
