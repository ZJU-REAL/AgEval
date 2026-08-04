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


def _builtin_codex_factory(
    model: str = "gpt-5.4-mini",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> Any:
    # Spec 19 Phase 5: no private codex stdout path.
    raise KeyError("executor 'codex' migrated to executor: acp with options.entry='codex'")


def _builtin_openai_factory(
    model: str = "gpt-4.1-mini",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> Any:
    from bora.adapters.agent_openai_http import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(model=model, base_url=base_url, api_key_env=api_key)


def _builtin_pi_factory(
    model: str = "claude-haiku-4-5",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> Any:
    raise KeyError("executor 'pi' migrated to executor: acp with options.entry='pi'")


def _builtin_opencode_factory(
    model: str = "zai-coding-plan/glm-4.7",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> Any:
    raise KeyError(
        "executor 'opencode' migrated to executor: acp with options.entry='opencode'"
    )


def _builtin_acp_factory(
    model: str = "entry-default",
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    entry: str | None = None,
    entry_id: str | None = None,
    **_kw: Any,
) -> Any:
    from bora.adapters.agent_acp import AcpExecutor

    eid = entry or entry_id
    if not eid:
        raise KeyError("acp_entry_required")
    return AcpExecutor(
        entry_id=str(eid),
        model=model,
        base_url=base_url,
        api_key_env=api_key,
    )


def _load_builtins() -> None:
    if _BUILTIN:
        return
    _BUILTIN["acp"] = _builtin_acp_factory
    _BUILTIN["codex"] = _builtin_codex_factory
    _BUILTIN["pi"] = _builtin_pi_factory
    _BUILTIN["opencode"] = _builtin_opencode_factory
    _BUILTIN["openai-http"] = _builtin_openai_factory
    _BUILTIN["openai"] = _builtin_openai_factory
    _BUILTIN["openai_responses"] = _builtin_openai_factory
    # claude-code residual: register only when binary exists (honest residual otherwise).

    # Residual kind name kept for inventory discoverability only; invoke is tombstone.
    def _claude_factory(
        model: str = "claude-haiku-4-5",
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        **_kw: Any,
    ) -> Any:
        raise KeyError(
            "executor 'claude-code' migrated to executor: acp with options.entry='claude-code'"
        )

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


def resolve_executor(
    kind: str,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    entry: str | None = None,
    entry_id: str | None = None,
    **_kw: Any,
) -> Any:
    """Resolve locked executor kind → entry point first, then builtin.

    ``api_key`` is an environment variable *name* (locator), never a secret value.
    ``base_url`` is optional non-secret upstream endpoint routing.
    ``entry`` / ``entry_id`` select the ACP registry row when ``kind == \"acp\"``.
    """
    _load_builtins()
    kwargs: dict[str, Any] = {"model": model}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    if entry:
        kwargs["entry"] = entry
    if entry_id:
        kwargs["entry_id"] = entry_id
    # Entry points take precedence so third-party wheels can override/extend.
    try:
        eps = entry_points(group="bora.agent_executors")
    except TypeError:
        eps = entry_points().get("bora.agent_executors", [])  # type: ignore[assignment]
    for ep in eps:
        if ep.name == kind:
            factory = ep.load()
            try:
                return factory(**kwargs)
            except TypeError:
                return factory(model=model)
    if kind in _BUILTIN:
        return _BUILTIN[kind](**kwargs)
    raise KeyError(kind)
