"""L1 host cleanup is owned by LifecycleStages.cleanup (Wave 1b)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from bora.application.attempt.attempt_stages import AttemptStageContext, DockerL1Stages
from bora.application.attempt.run_l1 import _l1_host_cleanup
from bora.runtime.coordinator import LifecycleCoordinator
from bora.runtime.identity import IdentityFactory
from bora.runtime.lifecycle import LifecyclePhase
from bora.runtime.outcomes import PhaseFact, PhaseStatus, RuntimeTerminalKind


def _attempt():
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "c" * 64)
    return factory.new_attempt(trial)


class FakeDocker:
    def __init__(self) -> None:
        self.cleanup_calls = 0
        self.stop_calls = 0

    def cleanup(self, runtime: SimpleNamespace) -> None:
        self.cleanup_calls += 1
        if getattr(runtime, "cleaned", False):
            return
        runtime.cleaned = True

    def stop_agent_targets(self, runtime: SimpleNamespace) -> None:
        self.stop_calls += 1

    def prepare_agent_targets(self, runtime: SimpleNamespace, topology, **_kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            targets={"t1": SimpleNamespace(public_view=lambda: {"id": "t1"})},
            actors={},
        )


class FakeCred:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.locator_keys: list[str] = []
        self.has_material = False
        self.cleanup_calls = 0

    def cleanup(self) -> None:
        self.cleanup_calls += 1


class FakeService:
    invocations_completed = 1


class FakeServer:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.stopped = False

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.stopped = True


def _image() -> SimpleNamespace:
    return SimpleNamespace(
        image_tag="bora-attempt:l1", image_digest="sha256:img", platform="linux/arm64"
    )


def _runtime(work: Path, attempt) -> SimpleNamespace:
    work.mkdir(parents=True, exist_ok=True)
    (work / "workspace").mkdir(exist_ok=True)
    return SimpleNamespace(
        attempt=attempt,
        workdir_host=work,
        image_lock=_image(),
        writer_stop_confirmed=True,
        writer_inventory=["agent"],
        cleaned=False,
        policy_digests={},
    )


def _lock() -> SimpleNamespace:
    return SimpleNamespace(
        digest="sha256:" + "c" * 64,
        task_id="sample",
        parameters={"harness_timeout_seconds": 5},
        agent_profiles=[{"id": "solver", "executor": "mock"}],
        provider={"kind": "docker"},
        limits={"agent_invocations": 1, "wall_time_seconds": 30},
        evaluation={
            "inputs": [{"artifact": "session-output", "target": "artifacts/session-output.json"}]
        },
        harness={"entrypoint": "harness:run"},
        provenance=None,
        job_overlay=None,
    )


def _install_l1_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    attempt,
    *,
    assemble_exc: Exception | None = None,
    eval_exc: Exception | None = None,
) -> tuple[FakeDocker, SimpleNamespace, FakeCred]:
    docker = FakeDocker()
    runtime = _runtime(tmp_path / "l1-work", attempt)
    cred = FakeCred(tmp_path / "cred")
    cred.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.prepare_l1_runtime",
        lambda *_a, **_k: (docker, runtime, {"containment": "full_l1_attempt"}),
    )

    def _fake_home_overlay(_lock, _value, *, ctx=None, **_k):  # type: ignore[no-untyped-def]
        if ctx is not None:
            ctx.cred = cred
            ctx.ledger = docker.prepare_agent_targets(
                runtime, SimpleNamespace(), cred_root=cred.root
            )
        return {"cred": cred}

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.hook_home_overlay",
        _fake_home_overlay,
    )
    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.seed_l1_workspace", lambda **_k: None
    )

    if assemble_exc is not None:

        def _boom_assemble(*_a: object, **_k: object) -> None:
            raise assemble_exc

        monkeypatch.setattr(
            "bora.application.attempt.agent_service_assemble.assemble_parent_agent_service",
            _boom_assemble,
        )
    else:
        monkeypatch.setattr(
            "bora.application.attempt.agent_service_assemble.assemble_parent_agent_service",
            lambda **_k: (FakeService(), 30.0, object()),
        )

    monkeypatch.setattr("bora.runtime.agent_service_protocol.AgentServiceServer", FakeServer)

    async def _harness(*_a: object, **_k: object) -> dict[str, object]:
        hold = tmp_path / "hold"
        hold.mkdir(exist_ok=True)
        art = hold / "session-output.json"
        art.write_text('{"ok": true}\n', encoding="utf-8")
        return {
            "envelope": {
                "ok": True,
                "terminal": {"kind": "completed"},
                "published": {"session-output": str(art)},
            },
            "artifact_hold": str(hold),
        }

    monkeypatch.setattr("bora.application.attempt.run_harness.run_harness_package", _harness)

    if eval_exc is not None:

        def _boom_eval(*_a: object, **_k: object) -> None:
            raise eval_exc

        monkeypatch.setattr(
            "bora.application.attempt.run_l1_phases.run_clean_evaluator_container", _boom_eval
        )
    else:
        monkeypatch.setattr(
            "bora.application.attempt.run_l1_phases.run_clean_evaluator_container",
            lambda **_k: (
                {"status": "PASS", "score": 1.0},
                {"ok": True, "writer_stop_confirmed": True},
            ),
        )
    return docker, runtime, cred


@pytest.mark.asyncio
async def test_coordinator_still_cleans_once_on_evaluate_failure() -> None:
    stages = ScriptedLifecycleStages(fail_at=LifecyclePhase.EVALUATE)
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.cleanup_calls == 1
    assert stages.cleanup_calls == 1
    assert record.terminal == RuntimeTerminalKind.FAILED


@pytest.mark.asyncio
async def test_coordinator_run_raise_invokes_cleanup() -> None:
    class RaisingRun:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def prepare(self, attempt) -> PhaseFact:
            return PhaseFact(
                attempt=attempt, phase=LifecyclePhase.PREPARE, status=PhaseStatus.SUCCEEDED
            )

        async def run(self, attempt) -> PhaseFact:
            raise RuntimeError("stage-run-boom")

        async def seal(self, attempt) -> PhaseFact:
            return PhaseFact(
                attempt=attempt, phase=LifecyclePhase.SEAL, status=PhaseStatus.SUCCEEDED
            )

        async def evaluate(self, attempt) -> PhaseFact:
            return PhaseFact(
                attempt=attempt, phase=LifecyclePhase.EVALUATE, status=PhaseStatus.SUCCEEDED
            )

        async def bind(self, attempt) -> PhaseFact:
            return PhaseFact(
                attempt=attempt, phase=LifecyclePhase.BIND, status=PhaseStatus.SUCCEEDED
            )

        async def cleanup(self, attempt) -> PhaseFact:
            self.cleanup_calls += 1
            return PhaseFact(
                attempt=attempt, phase=LifecyclePhase.CLEANUP, status=PhaseStatus.SUCCEEDED
            )

    stages = RaisingRun()
    record = await LifecycleCoordinator(stages=stages).run(_attempt())
    assert record.terminal == RuntimeTerminalKind.FAILED
    assert record.cleanup_calls == 1
    assert stages.cleanup_calls == 1


@pytest.mark.asyncio
async def test_cleanup_noop_without_handles(tmp_path: Path) -> None:
    ctx = AttemptStageContext(package_root=tmp_path, lock=_lock(), run_dir=tmp_path / "run")
    ctx.run_dir.mkdir()
    stages = DockerL1Stages(ctx=ctx)
    fact = await stages.cleanup(_attempt())
    assert fact.status == PhaseStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_cleanup_idempotent_when_called_twice(tmp_path: Path) -> None:
    attempt = _attempt()
    docker = FakeDocker()
    runtime = _runtime(tmp_path / "l1-work", attempt)
    cred = FakeCred(tmp_path / "cred")
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=tmp_path / "run",
        docker=docker,
        runtime=runtime,
        cred=cred,
    )
    ctx.run_dir.mkdir()
    stages = DockerL1Stages(ctx=ctx)
    await stages.cleanup(attempt)
    await stages.cleanup(attempt)
    assert docker.cleanup_calls == 2
    assert runtime.cleaned is True
    assert cred.cleanup_calls == 2


@pytest.mark.asyncio
async def test_evaluate_raise_after_prepare_cleans_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = _attempt()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    docker, runtime, cred = _install_l1_fakes(
        monkeypatch,
        tmp_path,
        attempt,
        eval_exc=RuntimeError("evaluator-boom"),
    )
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=run_dir,
        attempt=attempt,
        keep_workspace=True,
    )
    stages = DockerL1Stages(ctx=ctx)
    record = await LifecycleCoordinator(stages=stages).run(attempt)
    assert record.terminal == RuntimeTerminalKind.FAILED
    assert record.cleanup_calls == 1
    assert docker.cleanup_calls == 1
    assert cred.cleanup_calls == 1
    assert runtime.cleaned is True
    assert ctx.docker is docker
    assert ctx.runtime is runtime


@pytest.mark.asyncio
async def test_assemble_raise_cleans_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempt = _attempt()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    docker, runtime, cred = _install_l1_fakes(
        monkeypatch,
        tmp_path,
        attempt,
        assemble_exc=RuntimeError("assemble-boom"),
    )
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=run_dir,
        attempt=attempt,
        keep_workspace=True,
    )
    stages = DockerL1Stages(ctx=ctx)
    record = await LifecycleCoordinator(stages=stages).run(attempt)
    assert record.terminal == RuntimeTerminalKind.FAILED
    assert record.cleanup_calls == 1
    assert docker.cleanup_calls == 1
    assert cred.cleanup_calls == 1
    assert runtime.cleaned is True


@pytest.mark.asyncio
async def test_success_path_cleanup_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempt = _attempt()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    docker, runtime, cred = _install_l1_fakes(monkeypatch, tmp_path, attempt)
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=run_dir,
        attempt=attempt,
        keep_workspace=True,
    )
    stages = DockerL1Stages(ctx=ctx)
    record = await LifecycleCoordinator(stages=stages).run(attempt)
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert record.cleanup_calls == 1
    assert docker.cleanup_calls == 1
    assert cred.cleanup_calls == 1
    assert runtime.cleaned is True
    # A second Coordinator-style cleanup must not raise.
    _l1_host_cleanup(docker, runtime, cred, run_dir, keep_workspace=True)
    assert docker.cleanup_calls == 2


@pytest.mark.asyncio
async def test_run_l1_harness_stops_agent_targets_before_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writers must be confirmed stopped in run finally, not only in cleanup."""
    from bora.application.attempt.run_l1_phases import run_l1_harness

    attempt = _attempt()
    docker, runtime, _cred = _install_l1_fakes(monkeypatch, tmp_path, attempt)
    server = FakeServer()
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=tmp_path / "run",
        attempt=attempt,
        docker=docker,
        runtime=runtime,
        agent_server=server,
        agent_service=FakeService(),
        workspace_host=tmp_path / "ws",
        wall_s=30.0,
    )
    ctx.run_dir.mkdir()
    await run_l1_harness(ctx)
    assert server.stopped is True
    assert docker.stop_calls == 1
    assert docker.cleanup_calls == 0
