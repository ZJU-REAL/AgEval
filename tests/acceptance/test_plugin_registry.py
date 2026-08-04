"""Spec 08: entry-point aware executor registry (ACP + openai-http)."""

from __future__ import annotations

from bora.adapters.agent_acp import AcpExecutor
from bora.adapters.agent_registry import discover_executor_kinds, resolve_executor


def test_discover_includes_builtins() -> None:
    kinds = discover_executor_kinds()
    assert "acp" in kinds
    assert "openai-http" in kinds
    assert "codex" not in kinds


def test_resolve_acp_and_openai() -> None:
    a = resolve_executor("acp", model="entry-default", entry="opencode")
    assert isinstance(a, AcpExecutor)
    o = resolve_executor("openai-http", model="gpt-4.1-mini")
    assert o is not None


def test_unknown_kind_raises() -> None:
    try:
        resolve_executor("not-a-real-executor", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
