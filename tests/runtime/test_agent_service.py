"""Parent Agent Service: multi-invoke, hard ceiling, close, profile binding."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from tests.helpers.extension_registry import registry_with_executor

from ageval.plugins.agent_result import AgentResult
from ageval.runtime.agent_service_protocol import (
    AgentServiceServer,
    agent_service_client_call,
)
from ageval.runtime.parent_agent_service import ParentAgentService


class _FakeExecutor:
    kind = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del timeout, workdir, collect_dir, redaction_sentinels
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


class _SentinelTypeErrorExecutor:
    """Raises TypeError only when redaction_sentinels is passed — must not downgrade."""

    kind = "poison"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del prompt, timeout, workdir, collect_dir
        self.calls += 1
        if redaction_sentinels is not None:
            raise TypeError("deliberate_sentinels_type_error")
        return AgentResult(
            model="poison",
            text="should-not-succeed",
            structured={"ok": True},
            ok=True,
        )


def test_multi_invoke_same_session_respects_limit() -> None:
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake-model"}],
        agent_invocation_limit=2,
        attempt_id="attempt_testmulti001",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
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
        attempt_id="attempt_testclose001",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
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
        attempt_id="attempt_testprof001",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
    )
    bad = svc.open_session(profile_id="nope")
    assert bad["ok"] is False
    assert bad["error"] == "unknown_profile"


def test_executor_type_error_not_swallowed_by_signature_downgrade() -> None:
    """Internal TypeError must surface as crash — not a quieter retry that succeeds."""
    poison = _SentinelTypeErrorExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "poison", "model": "m"}],
        agent_invocation_limit=2,
        attempt_id="attempt_testtypeerr001",
        offline_env="",
        extension_registry=registry_with_executor("poison", poison),
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    out = svc.invoke(session_id=sid, prompt="x")
    assert out["ok"] is False
    assert out["error"] == "TypeError"
    assert poison.calls == 1
    assert out.get("text") != "should-not-succeed"


def test_unix_socket_server_open_invoke_close(monkeypatch: pytest.MonkeyPatch) -> None:
    # Client helper also honors offline gate before the Unix round-trip.
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "codex-mini", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        attempt_id="attempt_testsock001",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
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
