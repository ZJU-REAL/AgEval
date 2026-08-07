"""Shared ACP adapter type aliases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Optional process launcher: (command, args, env, cwd) -> provides streams.
# Host default uses acp.spawn_agent_process. L1 injects docker-exec launcher.
ProcessLauncher = Callable[..., Any]
