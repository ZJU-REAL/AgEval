"""openai-http first-party executor provide (API client path)."""

from __future__ import annotations

from typing import Any

from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR

PLUGIN_ID = "openai-http"
PRIORITY = 120


def _factory(
    *,
    options: dict[str, Any] | None = None,
    profile_id: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    plugin_id: str | None = None,
    **_kwargs: Any,
) -> Any:
    del options, profile_id, plugin_id
    from ageval.adapters.agent_openai_http import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(model=model or "gpt-4.1-mini", base_url=base_url, api_key_env=api_key)


def register_openai_http_contrib(registry: ExtensionRegistry) -> None:
    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _factory,
        priority=PRIORITY,
        source="first-party",
        is_factory=True,
    )
    # Alias used by older profiles/tests.
    registry.provide(
        EXECUTOR,
        "openai",
        _factory,
        priority=PRIORITY + 1,
        source="first-party",
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "register_openai_http_contrib"]
