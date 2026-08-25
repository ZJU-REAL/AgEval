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
    del profile_id
    effort = None
    if isinstance(options, dict):
        raw = options.get("reasoning_effort")
        if isinstance(raw, str) and raw.strip():
            effort = raw.strip()
        elif raw not in (None, ""):
            raise ValueError(
                "openai-http options.reasoning_effort must be a string when set"
            )
    from ageval.plugins.contrib.openai_http.executor import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(
        model=model or "gpt-4.1-mini",
        base_url=base_url,
        api_key_env=api_key,
        reasoning_effort=effort,
    )


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
