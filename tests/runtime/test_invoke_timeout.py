"""Per-invoke timeout is package/env-configurable (not hardcoded 300s)."""

from __future__ import annotations

import time

from tests.helpers.extension_registry import registry_with_executor

from ageval.plugins.agent_result import AgentResult
from ageval.runtime.parent_agent_service import (
    ParentAgentService,
    resolve_invoke_timeout_seconds,
)


class _CaptureTimeout:
    def __init__(self) -> None:
        self.last_timeout: float | None = None

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        t = kwargs.get("timeout")
        if t is None:
            self.last_timeout = None
        else:
            self.last_timeout = float(t)  # type: ignore[arg-type]
        return AgentResult(
            model="m", text='{"ok":true}', structured={"ok": True}, ok=True, events=()
        )


def test_resolve_invoke_timeout_from_params() -> None:
    assert resolve_invoke_timeout_seconds({"agent_timeout_seconds": 900}) == 900.0
    assert resolve_invoke_timeout_seconds({"agent_invoke_timeout_seconds": 1200}) == 1200.0
    assert resolve_invoke_timeout_seconds({}) == 300.0
    assert resolve_invoke_timeout_seconds({"agent_timeout_seconds": 0}) == 300.0
    assert resolve_invoke_timeout_seconds({"agent_timeout_seconds": -1}) == 300.0


def test_invoke_passes_configured_timeout(monkeypatch: object) -> None:
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)  # type: ignore[attr-defined]
    fake = _CaptureTimeout()
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "fake", "model": "m"}],
        agent_invocation_limit=3,
        attempt_id="a",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        invoke_timeout_seconds=777.0,
    )
    sid = svc.open_session(profile_id="p")["session_id"]
    out = svc.invoke(session_id=sid, prompt="hi")
    assert out["ok"] is True
    assert fake.last_timeout == 777.0


def test_env_override_wins_over_field(monkeypatch: object) -> None:
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)  # type: ignore[attr-defined]
    fake = _CaptureTimeout()
    monkeypatch.setenv("AGEVAL_AGENT_INVOKE_TIMEOUT", "42")  # type: ignore[attr-defined]
    try:
        svc = ParentAgentService(
            profiles=[{"id": "p", "executor": "fake", "model": "m"}],
            agent_invocation_limit=3,
            attempt_id="a",
            offline_env="",
            extension_registry=registry_with_executor("fake", fake),
            invoke_timeout_seconds=900.0,
        )
        sid = svc.open_session(profile_id="p")["session_id"]
        svc.invoke(session_id=sid, prompt="hi")
        assert fake.last_timeout == 42.0
    finally:
        monkeypatch.delenv("AGEVAL_AGENT_INVOKE_TIMEOUT", raising=False)  # type: ignore[attr-defined]


def test_invoke_timeout_capped_by_remaining_wall(monkeypatch: object) -> None:
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)  # type: ignore[attr-defined]
    fake = _CaptureTimeout()
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "fake", "model": "m"}],
        agent_invocation_limit=3,
        attempt_id="a",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        invoke_timeout_seconds=900.0,
        deadline_monotonic=time.monotonic() + 12.0,
    )
    sid = svc.open_session(profile_id="p")["session_id"]
    svc.invoke(session_id=sid, prompt="hi")
    assert fake.last_timeout is not None
    assert fake.last_timeout <= 12.0 + 0.5
    assert fake.last_timeout < 900.0
