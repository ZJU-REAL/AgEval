"""openai-http first-party executor provide (API client path)."""

from __future__ import annotations

from typing import Any

from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR

PLUGIN_ID = "openai-http"
PRIORITY = 120


def build_openai_http_executor(
    *,
    options: dict[str, Any] | None = None,
    profile_id: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kwargs: Any,
) -> Any:
    """Bind the ``executor`` slot for a plain HTTP API backend (no box needed)."""
    del options, profile_id
    from ageval.plugins.contrib.openai_http.executor import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(model=model or "gpt-4.1-mini", base_url=base_url, api_key_env=api_key)


def register_openai_http_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        EXECUTOR,
        PLUGIN_ID,
        build_openai_http_executor,
        priority=PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "register_openai_http_contrib"]
