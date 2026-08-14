"""#71 A: before/after_agent_open|close + normalize_agent_result are production-emitted."""

from __future__ import annotations

from typing import Any

from tests.helpers.extension_registry import registry_with_executor

from bora.plugins.slots import (
    AFTER_AGENT_CLOSE,
    AFTER_AGENT_OPEN,
    BEFORE_AGENT_CLOSE,
    BEFORE_AGENT_INVOKE,
    BEFORE_AGENT_OPEN,
    NORMALIZE_AGENT_RESULT,
)
from bora.runtime.parent_agent_service import ParentAgentService


class _FakeResult:
    def __init__(self, text: str = "ok") -> None:
        self.ok = True
        self.error = None
        self.text = text
        self.structured = None
        self.events = ()
        self.usage = None
        self.model = "fake"
        self.metadata = {}
        self.source_refs = ()
        self.stderr = ""


class _FakeExecutor:
    kind = "fake"

    def __init__(self) -> None:
        self.closed = False
        self.invokes: list[str] = []

    def invoke(self, prompt: str, **_kwargs: Any) -> _FakeResult:
        self.invokes.append(prompt)
        return _FakeResult(text=f"echo:{prompt}")

    def close(self) -> None:
        self.closed = True


def _svc_with_spies() -> tuple[ParentAgentService, _FakeExecutor, list[str]]:
    calls: list[str] = []
    executor = _FakeExecutor()

    async def before_open(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("before_agent_open")
        out = await nxt(value)
        if isinstance(out, dict):
            return {**out, "open_tag": "before"}
        return out

    async def after_open(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("after_agent_open")
        out = await nxt(value)
        if isinstance(out, dict):
            return {**out, "open_after": True}
        return out

    async def before_close(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("before_agent_close")
        return await nxt(value)

    async def after_close(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("after_agent_close")
        return await nxt(value)

    async def normalize(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("normalize_agent_result")
        out = await nxt(value)
        if hasattr(out, "text"):
            out.text = f"norm:{out.text}"
        return out

    async def rewrite_prompt(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("before_agent_invoke")
        if isinstance(value, str):
            value = f"{value}|rewritten"
        return await nxt(value)

    reg = registry_with_executor("fake", executor, priority=10)
    reg.on(BEFORE_AGENT_OPEN, "spy", before_open, priority=10, source="test")
    reg.on(AFTER_AGENT_OPEN, "spy", after_open, priority=10, source="test")
    reg.on(BEFORE_AGENT_CLOSE, "spy", before_close, priority=10, source="test")
    reg.on(AFTER_AGENT_CLOSE, "spy", after_close, priority=10, source="test")
    reg.on(NORMALIZE_AGENT_RESULT, "spy", normalize, priority=10, source="test")
    reg.on(BEFORE_AGENT_INVOKE, "spy", rewrite_prompt, priority=10, source="test")

    svc = ParentAgentService(
        profiles=[
            {
                "id": "p1",
                "executor": "fake",
                "model": "m",
                "extensions": [{"plugin": "spy"}],
            }
        ],
        agent_invocation_limit=5,
        attempt_id="att_test",
        offline_env="",
        extension_registry=reg,
    )
    return svc, executor, calls


def test_open_close_and_normalize_emit_in_order() -> None:
    svc, executor, calls = _svc_with_spies()
    opened = svc.open_session(profile_id="p1")
    assert opened["ok"] is True
    sid = opened["session_id"]
    assert "before_agent_open" in calls
    assert "after_agent_open" in calls

    inv = svc.invoke(session_id=sid, prompt="hi")
    assert inv["ok"] is True
    assert inv["text"] == "norm:echo:hi|rewritten"
    assert "normalize_agent_result" in calls
    assert "before_agent_invoke" in calls

    closed = svc.close_session(session_id=sid)
    assert closed["ok"] is True
    assert executor.closed is True
    assert "before_agent_close" in calls
    assert "after_agent_close" in calls
    # Order: open bookends before invoke; before_close before after_close.
    assert calls.index("before_agent_open") < calls.index("after_agent_open")
    assert calls.index("after_agent_open") < calls.index("before_agent_invoke")
    assert calls.index("normalize_agent_result") < calls.index("before_agent_close")
    assert calls.index("before_agent_close") < calls.index("after_agent_close")


def test_open_hook_fail_closed_no_half_open_session() -> None:
    executor = _FakeExecutor()
    reg = registry_with_executor("fake", executor, priority=10)

    async def boom(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx, value, nxt
        raise RuntimeError("open_denied")

    reg.on(BEFORE_AGENT_OPEN, "spy", boom, priority=10, source="test")
    svc = ParentAgentService(
        profiles=[
            {
                "id": "p1",
                "executor": "fake",
                "model": "m",
                "extensions": [{"plugin": "spy"}],
            }
        ],
        agent_invocation_limit=2,
        attempt_id="att_fail",
        offline_env="",
        extension_registry=reg,
    )
    opened = svc.open_session(profile_id="p1")
    assert opened["ok"] is False
    assert opened["error"] == "agent_open_hook_failed"
    assert svc._sessions == {}


def test_prompt_rewrite_short_circuit_path_still_uses_chain() -> None:
    """Prove multi-slot rewrite (constitution §1) on before_agent_invoke."""
    svc, _executor, calls = _svc_with_spies()
    sid = svc.open_session(profile_id="p1")["session_id"]
    inv = svc.invoke(session_id=sid, prompt="x")
    assert inv["ok"] is True
    assert "rewritten" in inv["text"]
    assert "before_agent_invoke" in calls
