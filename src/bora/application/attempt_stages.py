"""Production LifecycleStages adapters for L0 (local) and L1 (docker).

Shared skeleton (deadline, agent service, seal facts) lives in the helpers these
adapters call. Differences stay here: host evaluator vs clean container, and
whether agent targets are prepared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bora.runtime.identity import AttemptIdentity
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
    # Outputs filled by stages.
    exit_code: int = 2
    result_doc: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


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
    _ran: bool = False

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact:
        # Prepare remains owned by run_command (lock/evidence/env). This stage
        # records that the L0 adapter was selected.
        return _fact(attempt, LifecyclePhase.PREPARE, detail={"adapter": "local_l0"})

    async def run(self, attempt: AttemptIdentity) -> PhaseFact:
        # Body still executed by run_command for this slice; marker only.
        self._ran = True
        return _fact(attempt, LifecyclePhase.RUN, detail={"adapter": "local_l0"})

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.SEAL)

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.EVALUATE, detail={"evaluator": "host_subprocess"})

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.BIND)

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.CLEANUP)


@dataclass
class DockerL1Stages:
    """L1: clean-container evaluator; agent targets via Provider ledger."""

    ctx: AttemptStageContext

    async def prepare(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.PREPARE, detail={"adapter": "docker_l1"})

    async def run(self, attempt: AttemptIdentity) -> PhaseFact:
        from bora.application.run_l1 import run_l1_attempt

        code, doc, details = await run_l1_attempt(
            package_root=self.ctx.package_root,
            lock=self.ctx.lock,
            run_dir=self.ctx.run_dir,
            agent_meta=self.ctx.agent_meta,
            allow_offline_agent=self.ctx.allow_offline_agent,
            keep_workspace=self.ctx.keep_workspace,
        )
        self.ctx.exit_code = code
        self.ctx.result_doc = doc
        self.ctx.details = details
        status = str(doc.get("status") or "ERROR")
        # PASS/FAIL are runtime-success (evaluator authority elsewhere); ERROR fails the stage.
        runtime_ok = status in {"PASS", "FAIL"} or code in {0, 1}
        return _fact(
            attempt,
            LifecyclePhase.RUN,
            ok=runtime_ok,
            message=str((doc.get("error") or {}).get("kind") or ""),
            detail={"adapter": "docker_l1", "status": status},
        )

    async def seal(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.SEAL)

    async def evaluate(self, attempt: AttemptIdentity) -> PhaseFact:
        # Evaluator already ran inside run_l1_attempt; record containment fact only.
        return _fact(
            attempt,
            LifecyclePhase.EVALUATE,
            detail={"evaluator": "clean_container"},
        )

    async def bind(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.BIND)

    async def cleanup(self, attempt: AttemptIdentity) -> PhaseFact:
        return _fact(attempt, LifecyclePhase.CLEANUP)
