"""ageval Core 2 — Lifecycle: identity, state machine, coordinator, outcomes.

v0.2 delivers in-process Run/Trial/Attempt orchestration with test-double stages.
It does not start real Provider/Harness/Evaluator processes.
"""

from ageval.runtime.errors import LifecycleError
from ageval.runtime.identity import AttemptIdentity, RunIdentity, TrialIdentity
from ageval.runtime.outcomes import AttemptRecord, PhaseFact, RuntimeTerminalKind

__all__ = [
    "AttemptIdentity",
    "AttemptRecord",
    "LifecycleError",
    "PhaseFact",
    "RunIdentity",
    "RuntimeTerminalKind",
    "TrialIdentity",
]
