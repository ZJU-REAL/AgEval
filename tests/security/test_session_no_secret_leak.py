"""Spec 06 security: session evidence must not embed host credential bytes."""

from __future__ import annotations

import json

from bora.adapters.agent_contract import AgentResult
from bora.runtime.parent_agent_service import ParentAgentService


def test_parent_service_response_has_no_secret_keys() -> None:
    class Ex:
        def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
            return AgentResult(
                model="m",
                text='{"answer":1}',
                structured={"answer": 1},
                ok=True,
            )

    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        resolve_executor=lambda kind, model: Ex(),  # noqa: ARG005
        attempt_id="attempt_sec001",
    )
    sid = svc.open_session(profile_id="p")["session_id"]
    resp = svc.invoke(session_id=sid, prompt="hi")
    blob = json.dumps(resp)
    for forbidden in ("OPENAI_API_KEY", "sk-", "password", "token", "CODEX_HOME"):
        assert forbidden not in blob
    assert resp.get("provider_session_handle") is None
