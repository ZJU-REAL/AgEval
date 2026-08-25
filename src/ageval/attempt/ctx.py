"""AttemptCtx — the only object phases and plugins share.

The field list is deliberately closed. A phase or plugin that needs something
new must get it here explicitly, so "what can a plugin touch" stays readable.
PASS enters exactly once, through ``bind_evaluation``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ageval.config.model import LockedTaskConfig
from ageval.environments.protocol import EnvironmentProvider
from ageval.plugins.protocol import ExtensionGraph
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.services import ServiceTable
from ageval.runtime.cancellation import CancellationSignal


class EvaluationBindingError(RuntimeError):
    """Raised when something other than the evaluate phase tries to set the verdict."""


@dataclass
class PhaseFact:
    """One recorded fact from a phase or a chain handler."""

    phase: str
    name: str
    detail: dict[str, Any]


@dataclass
class AttemptCtx:
    """Everything one Attempt needs; nothing more."""

    run_id: str
    trial_id: str
    attempt_id: str
    lock: LockedTaskConfig
    profile_id: str
    bindings: ExtensionGraph
    registry: ExtensionRegistry
    services: ServiceTable
    host: EnvironmentProvider
    evidence: Any
    cancellation: CancellationSignal
    # Engine-owned locations: the member task directory and its dataset root.
    task_root: Path
    dataset_root: Path
    # Host-side upload sources. Phases never read the rest of the task tree.
    seed_dir: Path | None = None
    environment_src: Path | None = None
    evaluation_src: Path | None = None
    agent_service: Any = None
    deadline_monotonic: float | None = None
    keep_workspace: bool = False
    keep_vendor_raw: bool = False
    summary_extra: dict[str, Any] | None = None
    phase_facts: list[PhaseFact] = field(default_factory=list)
    phase: str = "created"
    evaluation_result: Any = None
    _writers_stopped: bool = False

    # --- verdict -------------------------------------------------------------

    def bind_evaluation(self, result: Any) -> None:
        """Bind the independent evaluator's result. The only source of PASS."""
        if self.phase != "evaluate":
            raise EvaluationBindingError(
                f"evaluation may only be bound from the evaluate phase (in {self.phase!r})"
            )
        if self.evaluation_result is not None:
            raise EvaluationBindingError("evaluation already bound for this Attempt")
        if not isinstance(result, dict):
            raise EvaluationBindingError("evaluator must return a dict")
        self.evaluation_result = result

    # --- budget --------------------------------------------------------------

    def remaining_seconds(self) -> float | None:
        """Seconds left before the Attempt deadline, or None when unbounded."""
        if self.deadline_monotonic is None:
            return None
        return max(0.0, self.deadline_monotonic - time.monotonic())

    def assert_deadline(self) -> None:
        remaining = self.remaining_seconds()
        if remaining is not None and remaining <= 0.0:
            raise TimeoutError("attempt wall time exceeded")

    # --- writers -------------------------------------------------------------

    def mark_writers_stopped(self) -> None:
        self._writers_stopped = True

    def assert_writers_stopped(self) -> None:
        """Evaluate must not start while the Agent side can still write."""
        if not self._writers_stopped:
            raise RuntimeError("agent writers not confirmed stopped before evaluate")

    # --- facts ---------------------------------------------------------------

    def record_fact(self, name: str, detail: dict[str, Any] | None = None) -> None:
        self.phase_facts.append(PhaseFact(phase=self.phase, name=name, detail=dict(detail or {})))

    def facts_as_list(self) -> list[dict[str, Any]]:
        return [
            {"phase": f.phase, "name": f.name, **({"detail": f.detail} if f.detail else {})}
            for f in self.phase_facts
        ]
