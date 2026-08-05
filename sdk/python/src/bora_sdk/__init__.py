"""bora_sdk — optional Harness Core surface for Task Package authors.

Does not own Run identity, Provider, credentials, or final PASS.
"""

from __future__ import annotations

from pathlib import Path

from bora_sdk.agent import Agent, AgentSession
from bora_sdk.context import HarnessContext, HarnessParameterView, RunScope
from bora_sdk.terminal import HarnessTerminal
from bora_sdk.tool import AllowList, CallLimit, Tool, ToolSet
from bora_sdk.workflow import bounded_gather, collect_results, first_success


def _load_version() -> str:
    try:
        from importlib.metadata import version

        return version("bora-sdk")
    except Exception:
        pass
    # Editable / source tree: sdk/python/VERSION → repo-root VERSION (symlink).
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


__all__ = [
    "Agent",
    "AgentSession",
    "AllowList",
    "CallLimit",
    "HarnessContext",
    "HarnessParameterView",
    "HarnessTerminal",
    "RunScope",
    "Tool",
    "ToolSet",
    "bounded_gather",
    "collect_results",
    "first_success",
]

__version__ = _load_version()

