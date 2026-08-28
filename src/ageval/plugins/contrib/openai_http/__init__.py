"""openai-http first-party executor provide (API client path)."""

from __future__ import annotations

import copy
from typing import Any

from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR

PLUGIN_ID = "openai-http"
PRIORITY = 120
_EXTRA_BODY_RESERVED = frozenset({"model", "api_key", "messages", "tools"})


def _as_extra_body(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        raise ValueError("openai-http options.extra_body must be a mapping when set")
    out: dict[str, Any] = {}
    reserved: list[str] = []
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("openai-http options.extra_body must be a mapping when set")
        name = key.strip()
        if name in _EXTRA_BODY_RESERVED:
            reserved.append(name)
            continue
        out[name] = copy.deepcopy(value)
    if reserved:
        raise ValueError("openai-http options.extra_body rejects " + ",".join(sorted(reserved)))
    return out


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
    extra_body: dict[str, Any] = {}
    if isinstance(options, dict):
        raw = options.get("reasoning_effort")
        if isinstance(raw, str) and raw.strip():
            effort = raw.strip()
        elif raw not in (None, ""):
            raise ValueError("openai-http options.reasoning_effort must be a string when set")
        extra_body = _as_extra_body(options.get("extra_body"))
    from ageval.plugins.contrib.openai_http.executor import OpenAIHTTPExecutor

    return OpenAIHTTPExecutor(
        model=model or "gpt-4.1-mini",
        base_url=base_url,
        api_key_env=api_key,
        reasoning_effort=effort,
        extra_body=extra_body,
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
