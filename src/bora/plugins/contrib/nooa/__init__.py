"""nooa first-party contrib: multi-slot provide/on for mechanism switch (Spec 02).

MVP: host-side SPI that loads package agent via options.agent / options.method.
L1 bake declaration for image_contribute. No legacy resolve_executor bridge.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from bora.adapters.agent_contract import AgentResult
from bora.plugins.errors import ExtensionMaterializeError
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import EXECUTOR, IMAGE_CONTRIBUTE, TRAJECTORY_COLLECT

PLUGIN_ID = "nooa"
# Distinct from acp (100) so unscoped priority order is stable; profiles still bind explicitly.
NOOA_PRIORITY = 110


class NooaExecutorSPI:
    """ExecutorSPI: invoke task-local agent class (options.agent + method)."""

    kind = "nooa"

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
        del base_url, api_key, plugin_id
        opts = dict(options or {})
        agent_ref = opts.get("agent")
        if not agent_ref or not str(agent_ref).strip():
            raise ExtensionMaterializeError(
                "nooa_options_agent_required",
                kind="extension_materialize_failed",
            )
        self.agent_ref = str(agent_ref).strip()
        self.method = str(opts.get("method") or "run").strip() or "run"
        self.profile_id = profile_id
        self.model = model or "nooa"
        self.options = opts
        self._agent: Any = None
        self._ready = False

    def open(self, **kwargs: Any) -> None:
        del kwargs
        self._agent = self._load_agent()
        self._ready = True

    def close(self) -> None:
        self._agent = None
        self._ready = False

    def _load_agent(self) -> Any:
        # "module.path:ClassName" or "module.path"
        ref = self.agent_ref
        if ":" in ref:
            mod_name, cls_name = ref.split(":", 1)
        else:
            mod_name, cls_name = ref, None
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:  # noqa: BLE001
            raise ExtensionMaterializeError(
                f"nooa_agent_import_failed:{exc}",
                kind="extension_materialize_failed",
            ) from exc
        if cls_name:
            cls = getattr(mod, cls_name, None)
            if cls is None:
                raise ExtensionMaterializeError(
                    f"nooa_agent_class_missing:{cls_name}",
                    kind="extension_materialize_failed",
                )
            return cls() if callable(cls) else cls
        return mod

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del timeout, redaction_sentinels
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        if not self._ready or self._agent is None:
            try:
                self.open()
            except ExtensionMaterializeError as exc:
                return AgentResult(
                    model=self.model,
                    text="",
                    structured=None,
                    ok=False,
                    error=str(exc.message if hasattr(exc, "message") else exc),
                    metadata={"plugin": PLUGIN_ID},
                )
        method = getattr(self._agent, self.method, None)
        if method is None or not callable(method):
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"nooa_method_missing:{self.method}",
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        try:
            # Prefer method(prompt, workdir=...) then method(prompt).
            try:
                raw = method(prompt, workdir=workdir)
            except TypeError:
                raw = method(prompt)
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
                metadata={"plugin": PLUGIN_ID},
            )
        if isinstance(raw, AgentResult):
            return raw
        if isinstance(raw, dict):
            return AgentResult(
                model=self.model,
                text=str(raw.get("text") or ""),
                structured=raw.get("structured")
                if isinstance(raw.get("structured"), dict)
                else raw,
                ok=bool(raw.get("ok", True)),
                error=str(raw["error"]) if raw.get("error") else None,
                metadata={
                    "plugin": PLUGIN_ID,
                    "agent": self.agent_ref,
                    "collect_dir": str(collect_dir or ""),
                },
            )
        text = str(raw) if raw is not None else ""
        return AgentResult(
            model=self.model,
            text=text,
            structured=None,
            ok=True,
            metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
        )


def _nooa_factory(**kwargs: Any) -> NooaExecutorSPI:
    return NooaExecutorSPI(**kwargs)


async def _nooa_image_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    declare = {
        "plugin": PLUGIN_ID,
        "bake": ["nooa", "bora-executor-nooa"],
    }
    base = list(value) if isinstance(value, list) else []
    base.append(declare)
    return await nxt(base)


async def _nooa_trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    return await nxt(value)


def register_nooa_contrib(registry: ExtensionRegistry) -> None:
    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _nooa_factory,
        priority=NOOA_PRIORITY,
        source="first-party",
        is_factory=True,
    )
    registry.on(
        IMAGE_CONTRIBUTE,
        PLUGIN_ID,
        _nooa_image_contribute,
        priority=NOOA_PRIORITY,
        source="first-party",
    )
    registry.on(
        TRAJECTORY_COLLECT,
        PLUGIN_ID,
        _nooa_trajectory_collect,
        priority=NOOA_PRIORITY,
        source="first-party",
    )


__all__ = ["PLUGIN_ID", "NooaExecutorSPI", "register_nooa_contrib"]
