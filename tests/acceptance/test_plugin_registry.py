"""Spec 08: entry-point aware executor registry."""

from __future__ import annotations

from bora.adapters.agent_registry import discover_executor_kinds, resolve_executor


def test_discover_includes_builtins() -> None:
    kinds = discover_executor_kinds()
    assert "codex" in kinds
    assert "openai-http" in kinds


def test_resolve_codex_and_openai() -> None:
    c = resolve_executor("codex", model="gpt-5.4-mini")
    assert c is not None
    o = resolve_executor("openai-http", model="gpt-4.1-mini")
    assert o is not None


def test_unknown_kind_raises() -> None:
    try:
        resolve_executor("not-a-real-executor", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
