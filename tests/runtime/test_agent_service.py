"""Parent Agent Service: multi-invoke, hard ceiling, close, profile binding."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bora.adapters.agent_contract import AgentResult
from bora.runtime.agent_service import (
    AgentServiceServer,
    ParentAgentService,
    agent_service_client_call,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.prompts.append(prompt)
        # Echo a structured answer derived from call count for multi-invoke tests.
        n = len(self.prompts)
        return AgentResult(
            model="fake-model",
            text=f'{{"answer": {40 + n}}}',
            structured={"answer": 40 + n, "n": n},
            ok=True,
            error=None,
        )


def test_multi_invoke_same_session_respects_limit() -> None:
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake-model"}],
        agent_invocation_limit=2,
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_testmulti001",
    )
    opened = svc.open_session(profile_id="p1")
    assert opened["ok"] is True
    sid = opened["session_id"]
    r1 = svc.invoke(session_id=sid, prompt="first")
    r2 = svc.invoke(session_id=sid, prompt="second")
    r3 = svc.invoke(session_id=sid, prompt="third")
    assert r1["ok"] and r1["structured"]["answer"] == 41
    assert r2["ok"] and r2["structured"]["answer"] == 42
    assert r3["ok"] is False and r3["error"] == "agent_invocation_limit"
    assert svc.invocations_completed == 2
    assert len(fake.prompts) == 2


def test_closed_session_rejects_invoke() -> None:
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=4,
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_testclose001",
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    svc.close_session(session_id=sid)
    denied = svc.invoke(session_id=sid, prompt="x")
    assert denied["ok"] is False
    assert denied["error"] == "session_closed"


def test_unknown_profile_fail_closed() -> None:
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=1,
        resolve_executor=lambda kind, model: (_ for _ in ()).throw(AssertionError("no")),  # noqa: ARG005
        attempt_id="attempt_testprof001",
    )
    bad = svc.open_session(profile_id="nope")
    assert bad["ok"] is False
    assert bad["error"] == "unknown_profile"


def test_unix_socket_server_open_invoke_close() -> None:
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "codex-mini", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_testsock001",
    )
    with tempfile.TemporaryDirectory() as tmp:
        sock = Path(tmp) / "ags.sock"
        server = AgentServiceServer(svc, sock)
        server.start()
        try:
            opened = agent_service_client_call(
                str(sock),
                {"op": "open", "profile_id": "codex-mini", "attempt_id": "ignored_client"},
            )
            assert opened["ok"] is True
            assert opened["attempt_id"] == "attempt_testsock001"
            sid = opened["session_id"]
            inv = agent_service_client_call(
                str(sock),
                {"op": "invoke", "session_id": sid, "prompt": "hi"},
            )
            assert inv["ok"] is True
            assert inv["structured"]["answer"] == 41
            closed = agent_service_client_call(str(sock), {"op": "close", "session_id": sid})
            assert closed["ok"] is True
            after = agent_service_client_call(
                str(sock),
                {"op": "invoke", "session_id": sid, "prompt": "again"},
            )
            assert after["ok"] is False
            assert after["error"] == "session_closed"
        finally:
            server.stop()
