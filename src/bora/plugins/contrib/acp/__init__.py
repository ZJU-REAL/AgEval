"""ACP first-party contrib: provide(executor) + image/trajectory hooks (Spec 01).

Not a full external ACP plugin package. Wrappers live here; protocol client code
may remain under ``bora.adapters.acp`` and is imported by the factory.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import (
    EXECUTOR,
    IMAGE_CONTRIBUTE,
    TRAJECTORY_COLLECT,
)

PLUGIN_ID = "acp"
# Stronger than default multi (1000); weaker than explicit profile binding.
ACP_PRIORITY = 100


class AcpExecutorSPI:
    """ExecutorSPI facade over adapters.acp.AcpExecutor."""

    kind = "acp"

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        profile_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        plugin_id: str | None = None,
        **_kwargs: Any,
    ) -> None:
        del plugin_id
        opts = dict(options or {})
        entry = opts.get("entry") or opts.get("entry_id")
        if not entry or not str(entry).strip():
            from bora.plugins.errors import ExtensionMaterializeError

            raise ExtensionMaterializeError(
                "acp_entry_required",
                kind="extension_materialize_failed",
            )
        from bora.adapters.acp import AcpExecutor

        self.profile_id = profile_id
        self._inner = AcpExecutor(
            entry_id=str(entry).strip(),
            model=model or "entry-default",
            base_url=base_url,
            api_key_env=api_key,
        )

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        if hasattr(self._inner, "close"):
            self._inner.close()

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> Any:
        try:
            return self._inner.invoke(
                prompt,
                timeout=timeout,
                workdir=workdir,
                collect_dir=collect_dir,
                redaction_sentinels=redaction_sentinels,
            )
        except TypeError:
            return self._inner.invoke(prompt, timeout=timeout)


def _acp_factory(**kwargs: Any) -> AcpExecutorSPI:
    return AcpExecutorSPI(**kwargs)


async def _acp_image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    """Declare official ACP entry bake requirements (merged into list)."""
    declare = {
        "plugin": PLUGIN_ID,
        "bake": "acp_entries",
        "entries": ["pi", "codex", "claude", "opencode", "grok-build"],
    }
    base = value if isinstance(value, list) else []
    base = list(base)
    base.append(declare)
    return await nxt(base)


async def _acp_trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Pass-through; concrete collect remains on AcpExecutor / evidence path."""
    return await nxt(value)


def register_acp_contrib(registry: ExtensionRegistry) -> None:
    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _acp_factory,
        priority=ACP_PRIORITY,
        source="first-party",
        is_default=False,
        is_factory=True,
    )
    registry.on(
        IMAGE_CONTRIBUTE,
        PLUGIN_ID,
        _acp_image_contribute,
        priority=ACP_PRIORITY,
        source="first-party",
    )
    registry.on(
        TRAJECTORY_COLLECT,
        PLUGIN_ID,
        _acp_trajectory_collect,
        priority=ACP_PRIORITY,
        source="first-party",
    )


__all__ = ["PLUGIN_ID", "AcpExecutorSPI", "register_acp_contrib"]
