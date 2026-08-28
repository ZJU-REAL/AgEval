"""anthropic-http first-party executor (Anthropic Messages API)."""

from __future__ import annotations

import copy
from typing import Any

from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR

PLUGIN_ID = "anthropic-http"
PRIORITY = 120
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_VERSION = "2023-06-01"
_EXTRA_BODY_RESERVED = frozenset({"model", "api_key", "messages", "tools", "system", "max_tokens"})


def _as_extra_body(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        raise ValueError("anthropic-http options.extra_body must be a mapping when set")
    out: dict[str, Any] = {}
    reserved: list[str] = []
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("anthropic-http options.extra_body must be a mapping when set")
        name = key.strip()
        if name in _EXTRA_BODY_RESERVED:
            reserved.append(name)
            continue
        out[name] = copy.deepcopy(value)
    if reserved:
        raise ValueError("anthropic-http options.extra_body rejects " + ",".join(sorted(reserved)))
    return out


def _as_max_tokens(raw: Any) -> int:
    if raw is None or raw == "":
        return _DEFAULT_MAX_TOKENS
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("anthropic-http options.max_tokens must be a positive int")
    if raw < 1:
        raise ValueError("anthropic-http options.max_tokens must be a positive int")
    return raw


def _as_version(raw: Any) -> str:
    if raw is None or raw == "":
        return _DEFAULT_VERSION
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("anthropic-http options.anthropic_version must be a string when set")
    return raw.strip()


def build_anthropic_http_executor(
    *,
    options: dict[str, Any] | None = None,
    profile_id: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kwargs: Any,
) -> Any:
    """Bind the ``executor`` slot for Anthropic Messages (no box needed)."""
    del profile_id
    extra_body: dict[str, Any] = {}
    max_tokens = _DEFAULT_MAX_TOKENS
    version = _DEFAULT_VERSION
    if isinstance(options, dict):
        max_tokens = _as_max_tokens(options.get("max_tokens"))
        version = _as_version(options.get("anthropic_version"))
        extra_body = _as_extra_body(options.get("extra_body"))
    from ageval.plugins.contrib.anthropic_http.executor import AnthropicHTTPExecutor

    return AnthropicHTTPExecutor(
        model=model or "claude-sonnet-4-6",
        base_url=base_url,
        api_key_env=api_key,
        anthropic_version=version,
        max_tokens=max_tokens,
        extra_body=extra_body,
    )


def register_anthropic_http_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        EXECUTOR,
        PLUGIN_ID,
        build_anthropic_http_executor,
        priority=PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "register_anthropic_http_contrib"]
