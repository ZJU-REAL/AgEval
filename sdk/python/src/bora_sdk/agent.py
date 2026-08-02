"""AgentSession / Agent thin facade (HC-2).

Logical Attempt-bound session only. Provider continuation remains unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class AgentSession:
    """Attempt-bound logical session (no provider resume token)."""

    attempt_id: str
    profile_id: str
    max_turns: int = 8
    _turns: int = 0
    _closed: bool = False
    provider_session_handle: None = None  # always null/unsupported for Codex

    async def invoke(self, prompt: str, **kwargs: Any) -> Mapping[str, Any]:
        if self._closed:
            raise RuntimeError("session closed")
        if kwargs:
            # Disallow profile/workspace/executor overrides mid-session.
            raise ValueError("session invoke does not accept profile overrides")
        if self._turns >= self.max_turns:
            raise RuntimeError("local max_turns exceeded")
        self._turns += 1
        # Parent Agent Service integration point — default offline stub.
        return {
            "text": "",
            "structured": {"answer": 42, "source": "session-stub"},
            "provider_session_handle": None,
            "turn": self._turns,
        }

    async def close(self) -> None:
        self._closed = True

    async def __aenter__(self) -> AgentSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


@dataclass
class Agent:
    """Thin facade that opens Attempt-bound sessions from context scope."""

    attempt_id: str

    def session(self, profile_id: str, *, max_turns: int = 8) -> AgentSession:
        return AgentSession(
            attempt_id=self.attempt_id,
            profile_id=profile_id,
            max_turns=max_turns,
        )
