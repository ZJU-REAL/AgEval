"""Wall hard ceiling is checked before external invoke."""

from __future__ import annotations

import time

from tests.helpers.extension_registry import registry_with_executor

from ageval.adapters.agent_contract import AgentResult
from ageval.runtime.parent_agent_service import ParentAgentService


class _Counting:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.n += 1
        return AgentResult(
            model="m", text='{"ok":true}', structured={"ok": True}, ok=True, events=()
        )


def test_wall_deadline_blocks_before_executor() -> None:
    fake = _Counting()
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "fake", "model": "m"}],
        agent_invocation_limit=5,
        attempt_id="a",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        deadline_monotonic=time.monotonic() - 1.0,  # already expired
    )
    opened = svc.open_session(profile_id="p")
    assert opened["ok"] is False
    assert opened["error"] == "wall_time_exceeded"
    assert fake.n == 0


def test_wall_deadline_blocks_mid_session() -> None:
    fake = _Counting()
    now = time.monotonic()
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "fake", "model": "m"}],
        agent_invocation_limit=5,
        attempt_id="a",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        deadline_monotonic=now + 0.05,
    )
    sid = svc.open_session(profile_id="p")["session_id"]
    time.sleep(0.08)
    denied = svc.invoke(session_id=sid, prompt="late")
    assert denied["ok"] is False
    assert denied["error"] == "wall_time_exceeded"
    assert fake.n == 0
