"""Offline Agent gate — one adapter over the operator env locator.

Production code must not scatter ``os.environ.get("BORA_OFFLINE_AGENT")``;
call :func:`is_offline_agent` (optionally with a custom env name from
``ParentAgentService.offline_env``).
"""

from __future__ import annotations

import os

DEFAULT_OFFLINE_ENV = "BORA_OFFLINE_AGENT"


def is_offline_agent(*, env_name: str = DEFAULT_OFFLINE_ENV) -> bool:
    """True when the operator forced offline Agent (fail closed)."""
    return os.environ.get(env_name) == "1"
