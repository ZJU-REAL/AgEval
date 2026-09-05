"""ACP first-party contrib: parent client, entry registry, executor SPI.

Not an external ``plugins/acp`` package and not installed via ``ageval plugin
install``. Official Attempt images bake every shipped entry; task recipes
also stack ``config.image_layers`` for the bound ``options.entry``.
"""

from __future__ import annotations

from typing import Any

from ageval.environments.protocol import Placement
from ageval.plugins.contrib.acp.executor import AcpExecutor
from ageval.plugins.contrib.acp.hooks import ENSURE_RUNTIME_PRIORITY, ensure_runtime
from ageval.plugins.contrib.acp.trajectory_map import acp_session_events_to_ageval
from ageval.plugins.contrib.acp.usage import normalize_acp_usage
from ageval.plugins.protocol import InjectRequirement
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import (
    AFTER_ENVIRONMENT_READY,
    ENVIRONMENT,
    EXECUTOR,
    TRAJECTORY_COLLECT,
)

PLUGIN_ID = "acp"
# Stronger than default multi (1000); weaker than explicit profile binding.
ACP_PRIORITY = 100


def build_acp_executor(
    *,
    options: dict[str, Any] | None = None,
    host: Any,
    placement: Placement,
    profile_id: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> AcpExecutor:
    """Bind the ``executor`` slot: one ACP entry attached to this Attempt's box."""
    del profile_id
    opts = dict(options or {})
    entry = _optional_str(opts.get("entry"))
    if entry is None:
        from ageval.plugins.errors import ExtensionMaterializeError

        raise ExtensionMaterializeError(
            "acp_entry_required",
            kind="extension_materialize_failed",
        )
    return AcpExecutor(
        entry_id=entry,
        host=host,
        placement=placement,
        model=model or "entry-default",
        reasoning_effort=_optional_str(opts.get("reasoning_effort")),
        base_url=base_url,
        api_key_env=api_key,
        idle_timeout_seconds=_optional_positive_seconds(opts.get("idle_timeout_seconds")),
    )


def _optional_str(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _optional_positive_seconds(raw: Any) -> float | None:
    """``options.idle_timeout_seconds``: unset / ≤0 disables; garbage fails closed."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        from ageval.plugins.errors import ExtensionMaterializeError

        raise ExtensionMaterializeError(
            "acp_idle_timeout_invalid",
            kind="extension_materialize_failed",
        )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        from ageval.plugins.errors import ExtensionMaterializeError

        raise ExtensionMaterializeError(
            "acp_idle_timeout_invalid",
            kind="extension_materialize_failed",
        ) from None
    return value if value > 0 else None


async def _acp_trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Tag trajectory payload as ACP-sourced; seal path writes from chain output (#71 B)."""
    out = await nxt(value)
    if isinstance(out, dict):
        meta = dict(out.get("metadata") or {})
        meta.setdefault("trajectory_source", "acp")
        return {**out, "metadata": meta}
    return out


def register_acp_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        EXECUTOR,
        PLUGIN_ID,
        build_acp_executor,
        priority=ACP_PRIORITY,
        source="first-party",
        is_factory=True,
    )
    registry.chain(
        AFTER_ENVIRONMENT_READY,
        PLUGIN_ID,
        ensure_runtime,
        priority=ENSURE_RUNTIME_PRIORITY,
        source="first-party",
        is_factory=True,
    )
    registry.chain(
        TRAJECTORY_COLLECT,
        PLUGIN_ID,
        _acp_trajectory_collect,
        priority=ACP_PRIORITY,
        source="first-party",
    )
    # The pipe always comes from the box, so the box must be able to attach one.
    registry.declare_inject(
        PLUGIN_ID,
        (InjectRequirement(service=ENVIRONMENT, capabilities=("attach_stdio",)),),
    )


__all__ = [
    "PLUGIN_ID",
    "AcpExecutor",
    "acp_session_events_to_ageval",
    "build_acp_executor",
    "ensure_runtime",
    "normalize_acp_usage",
    "register_acp_contrib",
]
