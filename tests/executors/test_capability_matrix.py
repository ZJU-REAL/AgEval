"""Executor capability matrix — ACP + openai-http only."""

from __future__ import annotations

from bora.adapters.agent_registry import discover_executor_kinds, resolve_executor
from bora.adapters.executor_capabilities import (
    BUILTIN_CAPABILITIES,
    get_capabilities,
    required_kinds_for_v014,
)


def test_acp_kind_registered() -> None:
    kinds = discover_executor_kinds()
    assert "Official/acp" in kinds
    assert "Official/openai-http" in kinds
    assert "codex" not in kinds
    assert "pi" not in kinds
    assert get_capabilities("Official/acp") is not None
    assert get_capabilities("Official/acp").execution_mode == "acp-stdio"  # type: ignore[union-attr]


def test_required_surface_is_acp() -> None:
    assert required_kinds_for_v014() == frozenset({"Official/acp"})


def test_capability_fields_frozen() -> None:
    for kind in ("Official/acp", "Official/openai-http"):
        cap = BUILTIN_CAPABILITIES[kind]
        assert cap.stream in {"native-events", "synthetic-lifecycle"}
        assert cap.execution_mode in {"cli-process", "api-client", "acp-stdio"}


def test_unknown_kind_keyerror() -> None:
    try:
        resolve_executor("not-a-real-executor", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_private_kinds_gone() -> None:
    for kind in ("codex", "pi", "opencode", "claude-code"):
        try:
            resolve_executor(kind, model="x")
            raise AssertionError(f"{kind} must KeyError")
        except KeyError:
            pass


def test_resolve_acp_constructor() -> None:
    ex = resolve_executor("Official/acp", model="entry-default", entry="opencode")
    assert getattr(ex, "kind", None) == "acp"
    # SPI may wrap adapters.acp.AcpExecutor
    inner = getattr(ex, "_inner", ex)
    assert getattr(inner, "entry_id", None) == "opencode"
