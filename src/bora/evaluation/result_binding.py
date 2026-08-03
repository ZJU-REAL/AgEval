"""Flat Result binding — independent of Harness terminal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FlatResult:
    status: str  # PASS | FAIL | ERROR
    score: float | None
    metrics: Mapping[str, Any]
    error_phase: str | None
    cleanup_warning: str | None
    evidence_path: str
    runtime_kind: str
    harness_kind: str
    agent_invocations: int
    assurance: str = "l0"
    # Result.logs is a locator to Attempt evidence root (design §8.9); not a score input.
    logs: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "assurance": self.assurance,
            "agent_invocations": self.agent_invocations,
            "cleanup_warning": self.cleanup_warning,
            "error": {"phase": self.error_phase} if self.error_phase else None,
            "evidence_path": self.evidence_path,
            "harness_kind": self.harness_kind,
            "logs": self.logs or self.evidence_path,
            "metrics": dict(self.metrics),
            "runtime_kind": self.runtime_kind,
            "score": self.score,
            "status": self.status,
        }


def bind_result(
    *,
    evaluator_raw: Mapping[str, Any] | None,
    harness_kind: str,
    runtime_kind: str,
    agent_invocations: int,
    evidence_path: str,
    cleanup_warning: str | None = None,
    error_phase: str | None = None,
    logs: str | None = None,
    assurance: str = "l0",
) -> FlatResult:
    locator = logs if logs is not None else evidence_path
    if error_phase:
        return FlatResult(
            status="ERROR",
            score=None,
            metrics={},
            error_phase=error_phase,
            cleanup_warning=cleanup_warning,
            evidence_path=evidence_path,
            runtime_kind=runtime_kind,
            harness_kind=harness_kind,
            agent_invocations=agent_invocations,
            assurance=assurance,
            logs=locator,
        )
    if evaluator_raw is None:
        return FlatResult(
            status="ERROR",
            score=None,
            metrics={},
            error_phase="evaluation",
            cleanup_warning=cleanup_warning,
            evidence_path=evidence_path,
            runtime_kind=runtime_kind,
            harness_kind=harness_kind,
            agent_invocations=agent_invocations,
            assurance=assurance,
            logs=locator,
        )
    status = str(evaluator_raw.get("status", "FAIL"))
    score = evaluator_raw.get("score")
    score_f = float(score) if isinstance(score, int | float) else None
    raw_metrics = evaluator_raw.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    return FlatResult(
        status=status,
        score=score_f,
        metrics=metrics,
        error_phase=None,
        cleanup_warning=cleanup_warning,
        evidence_path=evidence_path,
        runtime_kind=runtime_kind,
        harness_kind=harness_kind,
        agent_invocations=agent_invocations,
        assurance=assurance,
        logs=locator,
    )
