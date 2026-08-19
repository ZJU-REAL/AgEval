"""SDK Agent.session accepts actor_id (Spec 18)."""

from __future__ import annotations

from ageval_sdk import Agent


def test_session_carries_actor_id() -> None:
    agent = Agent(attempt_id="attempt_x")
    session = agent.session("p1", actor_id="planner", max_turns=3)
    assert session.actor_id == "planner"
    assert session.profile_id == "p1"


def test_session_actor_id_optional_l0() -> None:
    agent = Agent(attempt_id="attempt_x")
    session = agent.session("p1")
    assert session.actor_id is None
