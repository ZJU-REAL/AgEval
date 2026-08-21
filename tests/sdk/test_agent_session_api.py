"""The SDK session surface: bounded turns, no authority, no invented success."""

from __future__ import annotations

import asyncio

import pytest
from ageval_sdk import Agent, AgentSession


def test_session_rejects_profile_overrides() -> None:
    session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=2)

    async def _run() -> None:
        with pytest.raises(ValueError, match="override"):
            await session.invoke("hi", profile_id="other")

    asyncio.run(_run())


def test_unbound_session_reports_failure_instead_of_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGEVAL_AGENT_SERVICE_SOCK", raising=False)
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)
    session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=2)

    answer = asyncio.run(session.invoke("one"))

    assert answer["ok"] is False
    assert answer["error"] == "agent_session_unbound"
    assert answer["text"] == ""
    assert answer["structured"] is None


def test_offline_gate_refuses_before_the_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_OFFLINE_AGENT", "1")
    session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=2)

    answer = asyncio.run(session.invoke("one"))

    assert (answer["ok"], answer["error"]) == (False, "offline_forced")


def test_local_turn_budget_stops_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGEVAL_AGENT_SERVICE_SOCK", raising=False)
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)
    session = AgentSession(attempt_id="attempt_x", profile_id="p", max_turns=1)

    async def _run() -> None:
        await session.invoke("one")
        with pytest.raises(RuntimeError, match="max_turns"):
            await session.invoke("two")

    asyncio.run(_run())


def test_agent_facade_builds_session() -> None:
    session = Agent(attempt_id="attempt_abc").session("solver", max_turns=3)
    assert isinstance(session, AgentSession)
    assert session.profile_id == "solver"
    assert session.provider_session_handle is None
