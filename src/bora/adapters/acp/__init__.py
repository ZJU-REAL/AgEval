"""Single typed ACP executor package (Spec 19 / chore #31).

Parent/host only: spawns (or attaches to) an ACP entry process over stdio via
``agent-client-protocol``. Vendor private stdout scrape is forbidden.

Layout: usage · trajectory · client · executor.
"""

from __future__ import annotations

from bora.adapters.acp.executor import AcpExecutor
from bora.adapters.acp.resolve import resolve_acp_executor
from bora.adapters.acp.trajectory import write_trajectory_jsonl
from bora.adapters.acp.types import ProcessLauncher
from bora.adapters.acp.usage import normalize_acp_usage

__all__ = [
    "AcpExecutor",
    "ProcessLauncher",
    "normalize_acp_usage",
    "resolve_acp_executor",
    "write_trajectory_jsonl",
]
