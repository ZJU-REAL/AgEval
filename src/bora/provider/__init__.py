"""BORA Core 3 — Provider (L0 local process).

v0.3 delivers real local-process execution with process-group cleanup and
``assurance: l0``. It does not claim container isolation or ``isolated`` evidence.
"""

from bora.provider.contract import (
    ExecutableGrant,
    ProcessLaunchPlan,
    TerminationPolicy,
    WorkspacePlan,
)
from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind

__all__ = [
    "ExecutableGrant",
    "ProcessLaunchPlan",
    "ProcessOutcome",
    "ProcessTerminalKind",
    "TerminationPolicy",
    "WorkspacePlan",
]
