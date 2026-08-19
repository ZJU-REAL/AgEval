"""Spec 06 named SDK path: AgentSession contract (no Runtime authority)."""

from __future__ import annotations

import asyncio
import os

import pytest
from ageval_sdk import Agent, AgentSession


def test_session_rejects_profile_overrides() -> None:
    session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=2)

    async def _run() -> None:
        with pytest.raises(ValueError, match="override"):
            await session.invoke("hi", profile_id="other")

    asyncio.run(_run())


def test_local_max_turns_soft_stop() -> None:
    os.environ["AGEVAL_SDK_SESSION_STUB"] = "1"
    os.environ.pop("AGEVAL_AGENT_SERVICE_SOCK", None)
    try:
        session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=1)

        async def _run() -> None:
            first = await session.invoke("one")
            assert first.get("ok") is True
            with pytest.raises(RuntimeError, match="max_turns"):
                await session.invoke("two")

        asyncio.run(_run())
    finally:
        os.environ.pop("AGEVAL_SDK_SESSION_STUB", None)


def test_agent_facade_builds_session() -> None:
    agent = Agent(attempt_id="attempt_abc")
    session = agent.session("codex-mini", max_turns=3)
    assert isinstance(session, AgentSession)
    assert session.profile_id == "codex-mini"
    assert session.provider_session_handle is None
