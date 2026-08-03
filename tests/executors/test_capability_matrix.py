"""Built-in executor capability matrix freeze (v0.14 Phase 0)."""

from __future__ import annotations

from bora.adapters.agent_registry import discover_executor_kinds, resolve_executor
from bora.adapters.executor_capabilities import (
    BUILTIN_CAPABILITIES,
    get_capabilities,
    required_kinds_for_v014,
)


def test_required_kinds_registered() -> None:
    kinds = discover_executor_kinds()
    for k in required_kinds_for_v014():
        assert k in kinds
        assert get_capabilities(k) is not None


def test_capability_fields_frozen() -> None:
    for kind in ("codex", "pi", "opencode"):
        cap = BUILTIN_CAPABILITIES[kind]
        assert cap.stream in {"native-events", "synthetic-lifecycle"}
        assert cap.execution_mode in {"cli-process", "api-client"}
        assert cap.structured_output in {"native", "validated-text", "unsupported"}


def test_unknown_kind_keyerror() -> None:
    try:
        resolve_executor("not-a-real-executor", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_resolve_pi_and_opencode_constructors() -> None:
    pi = resolve_executor("pi", model="claude-haiku-4-5")
    assert getattr(pi, "kind", None) == "pi" or type(pi).__name__ == "PiExecutor"
    oc = resolve_executor("opencode", model="zai-coding-plan/glm-4.7")
    assert getattr(oc, "kind", None) == "opencode" or type(oc).__name__ == "OpenCodeExecutor"
