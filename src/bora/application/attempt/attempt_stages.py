"""Production LifecycleStages adapters for L0 (local) and L1 (docker).

Shared skeleton (deadline, agent service, seal facts) lives in the helpers these
adapters call. Differences stay here: host evaluator vs clean container, and
whether agent targets are prepared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bora.runtime.identity import AttemptIdentity, assert_same_attempt
from bora.runtime.lifecycle import LifecyclePhase
from bora.runtime.outcomes import PhaseFact, PhaseStatus


@dataclass
class AttemptStageContext:
    """Mutable bag of Attempt facts shared across coordinator stages."""

    package_root: Path
    lock: Any
    run_dir: Path
    agent_meta: dict[str, Any] = field(default_factory=dict)
    allow_offline_agent: bool = False
    keep_workspace: bool = False
    attempt: AttemptIdentity | None = None
    docker: Any = None
    runtime: Any = None
    cred: Any = None
    database_root: Path | None = None
    task_id: str = ""
    evidence_store: Any = None
    env_manager: Any = None
    agent_service: Any = None
    agent_server: Any = None
    agent_sock_path: Path | None = None
    authority: Any = None
    timer: Any = None
    harness_out: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)
    harness_kind: str = "failed"
    error_phase: str | None = None
    artifacts_map: dict[str, str] = field(default_factory=dict)
    evaluator_raw: dict[str, Any] | None = None
    eval_extension_meta: dict[str, Any] = field(default_factory=dict)
    eval_meta: dict[str, Any] = field(default_factory=dict)
    l1_meta: dict[str, Any] = field(default_factory=dict)
    inv_count: int = 0
    wall_s: float = 0.0
    workspace_host: Path | None = None
    ledger: Any = None
    topology: Any = None
    # Outputs filled by stages.
    exit_code: int = 2
    result_doc: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


def _bind_stage_attempt(ctx: AttemptStageContext, attempt: AttemptIdentity) -> None:
    """Record the Coordinator Attempt on the context; never mint a second chain."""
    if ctx.attempt is not None:
        assert_same_attempt(ctx.attempt, attempt)
    else:
        ctx.attempt = attempt
    ctx.agent_meta.setdefault("attempt_id", attempt.value)
    ctx.agent_meta.setdefault("trial_id", attempt.trial.value)
    ctx.agent_meta.setdefault("run_id", attempt.trial.run.value)


def _fact(
    attempt: AttemptIdentity,
    phase: LifecyclePhase,
    *,
    ok: bool = True,
    message: str = "",
    detail: dict[str, Any] | None = None,
) -> PhaseFact:
    return PhaseFact(
        attempt=attempt,
        phase=phase,
        status=PhaseStatus.SUCCEEDED if ok else PhaseStatus.FAILED,
        message=message,
        detail=detail or {},
    )


@dataclass
class LocalL0Stages:
    """L0: host subprocess evaluator; no agent-target ledger."""

    ctx: AttemptStageContext

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import prepare_l0_attempt

        _bind_stage_attempt(self.ctx, attempt)
        early = prepare_l0_attempt(self.ctx)
        if early is not None:
            return _fact(
                attempt,
                LifecyclePhase.PREPARE,
                ok=False,
                message="environment",
                detail={"adapter": "local_l0"},
            )
        return _fact(attempt, LifecyclePhase.PREPARE, detail={"adapter": "local_l0"})

    async def run(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import run_l0_harness

        _bind_stage_attempt(self.ctx, attempt)
        await run_l0_harness(self.ctx)
        return _fact(attempt, LifecyclePhase.RUN, detail={"adapter": "local_l0"})

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import seal_l0_inputs

        _bind_stage_attempt(self.ctx, attempt)
        seal_l0_inputs(self.ctx)
        return _fact(attempt, LifecyclePhase.SEAL)

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import evaluate_l0

        _bind_stage_attempt(self.ctx, attempt)
        evaluate_l0(self.ctx)
        return _fact(attempt, LifecyclePhase.EVALUATE, detail={"evaluator": "host_subprocess"})

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import bind_l0_result

        _bind_stage_attempt(self.ctx, attempt)
        bind_l0_result(self.ctx)
        return _fact(attempt, LifecyclePhase.BIND)

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l0 import cleanup_l0

        _bind_stage_attempt(self.ctx, attempt)
        cleanup_l0(self.ctx)
        return _fact(attempt, LifecyclePhase.CLEANUP, detail={"adapter": "local_l0"})


@dataclass
class DockerL1Stages:
    """L1: clean-container evaluator; agent targets via Provider ledger."""

    ctx: AttemptStageContext

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import prepare_l1_session

        _bind_stage_attempt(self.ctx, attempt)
        try:
            ok = prepare_l1_session(self.ctx)
        except Exception as exc:
            self.ctx.error_message = f"{type(exc).__name__}: {exc}"
            raise
        return _fact(
            attempt,
            LifecyclePhase.PREPARE,
            ok=ok,
            message=self.ctx.error_message
            or str((self.ctx.result_doc.get("error") or {}).get("kind") or ""),
            detail={"adapter": "docker_l1"},
        )

    async def run(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import run_l1_harness

        _bind_stage_attempt(self.ctx, attempt)
        try:
            await run_l1_harness(self.ctx)
        except Exception as exc:
            self.ctx.error_message = f"{type(exc).__name__}: {exc}"
            raise
        return _fact(attempt, LifecyclePhase.RUN, detail={"adapter": "docker_l1"})

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import seal_l1_inputs

        _bind_stage_attempt(self.ctx, attempt)
        ok = seal_l1_inputs(self.ctx)
        return _fact(
            attempt,
            LifecyclePhase.SEAL,
            ok=ok,
            message=str((self.ctx.result_doc.get("error") or {}).get("kind") or ""),
        )

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import evaluate_l1

        _bind_stage_attempt(self.ctx, attempt)
        evaluate_l1(self.ctx)
        return _fact(
            attempt,
            LifecyclePhase.EVALUATE,
            detail={"evaluator": "clean_container"},
        )

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import bind_l1_result

        _bind_stage_attempt(self.ctx, attempt)
        bind_l1_result(self.ctx)
        return _fact(attempt, LifecyclePhase.BIND)

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.attempt.run_l1_phases import cleanup_l1

        _bind_stage_attempt(self.ctx, attempt)
        cleanup_l1(self.ctx)
        return _fact(attempt, LifecyclePhase.CLEANUP, detail={"adapter": "docker_l1"})
