"""AgentExecutor plugin registry via package entry points (Spec 08).

Built-in executors register under group ``bora.agent_executors``. Third-party
wheels may contribute the same group without Core branching on task/bench names.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Protocol


class AgentExecutor(Protocol):
    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
    ) -> Any: ...


# First-party kinds always available even if entry points fail to load.
_BUILTIN: dict[str, Any] = {}


def _builtin_codex_factory(model: str = "gpt-5.4-mini", **_kw: Any) -> Any:
    from bora.adapters.agent_codex import CodexExecutor

    return CodexExecutor(model=model)


def _builtin_openai_factory(model: str = "gpt-4.1-mini", **_kw: Any) -> Any:
    from bora.adapters.agent_openai_http import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(model=model)


def _builtin_pi_factory(model: str = "claude-haiku-4-5", **_kw: Any) -> Any:
    from bora.adapters.agent_pi import PiExecutor

    return PiExecutor(model=model)


def _builtin_opencode_factory(model: str = "zai-coding-plan/glm-4.7", **_kw: Any) -> Any:
    from bora.adapters.agent_opencode import OpenCodeExecutor

    return OpenCodeExecutor(model=model)


def _load_builtins() -> None:
    if _BUILTIN:
        return
    _BUILTIN["codex"] = _builtin_codex_factory
    _BUILTIN["pi"] = _builtin_pi_factory
    _BUILTIN["opencode"] = _builtin_opencode_factory
    _BUILTIN["openai-http"] = _builtin_openai_factory
    _BUILTIN["openai"] = _builtin_openai_factory
    _BUILTIN["openai_responses"] = _builtin_openai_factory
    # claude-code residual: register only when binary exists (honest residual otherwise).
    import shutil

    if shutil.which("claude") or shutil.which("claude-code"):
        def _claude_factory(model: str = "claude-haiku-4-5", **_kw: Any) -> Any:
            from bora.adapters.agent_claude_code import ClaudeCodeExecutor

            return ClaudeCodeExecutor(model=model)

        _BUILTIN["claude-code"] = _claude_factory


def discover_executor_kinds() -> set[str]:
    """Return registered executor kind names (builtin + entry points)."""
    _load_builtins()
    kinds = set(_BUILTIN)
    try:
        eps = entry_points(group="bora.agent_executors")
    except TypeError:
        # Python <3.12 style
        eps = entry_points().get("bora.agent_executors", [])  # type: ignore[assignment]
    for ep in eps:
        kinds.add(ep.name)
    return kinds


def resolve_executor(kind: str, *, model: str) -> Any:
    """Resolve locked executor kind → entry point first, then builtin."""
    _load_builtins()
    # Entry points take precedence so third-party wheels can override/extend.
    try:
        eps = entry_points(group="bora.agent_executors")
    except TypeError:
        eps = entry_points().get("bora.agent_executors", [])  # type: ignore[assignment]
    for ep in eps:
        if ep.name == kind:
            factory = ep.load()
            return factory(model=model)
    if kind in _BUILTIN:
        return _BUILTIN[kind](model=model)
    raise KeyError(kind)
