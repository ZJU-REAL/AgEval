"""Builtin default contributions for every L0–L5 public slot.

Defaults are registered with plugin_id ``default``, high priority number (weak),
and may be replaced or unloaded via explicit binding / replace_default.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.middleware import passthrough_handler
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import (
    AFTER_AGENT_CLOSE,
    AFTER_AGENT_INVOKE,
    AFTER_AGENT_OPEN,
    AFTER_CLEANUP,
    AFTER_EVALUATE,
    AFTER_PREPARE,
    AFTER_RUN,
    BEFORE_AGENT_CLOSE,
    BEFORE_AGENT_INVOKE,
    BEFORE_AGENT_OPEN,
    BEFORE_CLEANUP,
    BEFORE_EVALUATE,
    BEFORE_PREPARE,
    BEFORE_RUN,
    CLEANUP_ACTIONS,
    CLEANUP_REPORT,
    DEFAULT_PRIORITY,
    ENV_ACTION,
    ENV_INJECT,
    ENV_PREPARE_COMMANDS,
    ENV_TEARDOWN_COMMANDS,
    EVALUATION_INPUT_CONTRIBUTE,
    EVALUATION_RUNTIME,
    EVIDENCE_EXTRA,
    EXECUTOR,
    IMAGE_CONTRIBUTE,
    NORMALIZE_AGENT_RESULT,
    SCORE_POSTPROCESS,
    TRAJECTORY_COLLECT,
    TRAJECTORY_ENRICH,
    TRAJECTORY_SEAL,
    SlotKind,
    get_slot_kind,
)

PLUGIN_ID = "default"


class DefaultExecutor:
    """Fallback executor when no profile-selected plugin is available.

    Bridges to the legacy ``resolve_executor`` path using the profile's
    ``executor`` field as kind. Spec 01 registers ACP as first-party contrib;
    explicit ``executor: acp`` then selects the acp provide instead of this.
    """

    kind = "default"

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
        self.options = dict(options or {})
        self.profile_id = profile_id
        self.model = model or "entry-default"
        self.base_url = base_url
        self.api_key = api_key
        self._inner: Any = None
        self._kind = str(self.options.get("_legacy_kind") or "acp")

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        inner = self._inner
        if inner is not None and hasattr(inner, "close"):
            inner.close()

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> Any:
        if self._inner is None:
            from bora.adapters.agent_registry import resolve_executor

            entry = self.options.get("entry")
            self._inner = resolve_executor(
                self._kind,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                entry=str(entry) if entry else None,
                entry_id=str(entry) if entry else None,
            )
        try:
            return self._inner.invoke(
                prompt,
                timeout=timeout,
                workdir=workdir,
                collect_dir=collect_dir,
                redaction_sentinels=redaction_sentinels,
            )
        except TypeError:
            try:
                return self._inner.invoke(prompt, timeout=timeout, collect_dir=collect_dir)
            except TypeError:
                return self._inner.invoke(prompt, timeout=timeout)


def _default_executor_factory(**kwargs: Any) -> DefaultExecutor:
    return DefaultExecutor(**kwargs)


def _identity_declare(**_kwargs: Any) -> dict[str, Any]:
    return {}


def _default_eval_runtime(**_kwargs: Any) -> dict[str, Any]:
    return {"runtime": "package", "source": "default"}


def _default_trajectory_seal(**_kwargs: Any) -> dict[str, Any]:
    """Authority shape marker — actual seal stays in evidence store path."""
    return {"seal": "default_authority_shape", "plugin": PLUGIN_ID}


def _default_env_action(**_kwargs: Any) -> dict[str, Any]:
    return {"action": "default_deny_unknown", "plugin": PLUGIN_ID}


def register_defaults(registry: ExtensionRegistry) -> None:
    """Register one default contribution for every public L0–L5 slot."""
    multi_slots = [
        BEFORE_PREPARE,
        AFTER_PREPARE,
        BEFORE_RUN,
        AFTER_RUN,
        BEFORE_EVALUATE,
        AFTER_EVALUATE,
        BEFORE_CLEANUP,
        AFTER_CLEANUP,
        IMAGE_CONTRIBUTE,
        ENV_PREPARE_COMMANDS,
        ENV_INJECT,
        ENV_TEARDOWN_COMMANDS,
        BEFORE_AGENT_OPEN,
        AFTER_AGENT_OPEN,
        BEFORE_AGENT_INVOKE,
        AFTER_AGENT_INVOKE,
        BEFORE_AGENT_CLOSE,
        AFTER_AGENT_CLOSE,
        NORMALIZE_AGENT_RESULT,
        EVALUATION_INPUT_CONTRIBUTE,
        SCORE_POSTPROCESS,
        TRAJECTORY_COLLECT,
        TRAJECTORY_ENRICH,
        EVIDENCE_EXTRA,
        CLEANUP_ACTIONS,
        CLEANUP_REPORT,
    ]
    for slot in multi_slots:
        assert get_slot_kind(slot) is SlotKind.MULTI
        registry.on(
            slot,
            PLUGIN_ID,
            passthrough_handler,
            priority=DEFAULT_PRIORITY,
            source="default",
            is_default=True,
            is_factory=False,
        )

    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _default_executor_factory,
        priority=DEFAULT_PRIORITY,
        source="default",
        is_default=True,
        is_factory=True,
    )
    registry.provide(
        ENV_ACTION,
        PLUGIN_ID,
        _default_env_action,
        priority=DEFAULT_PRIORITY,
        source="default",
        is_default=True,
        is_factory=True,
    )
    registry.provide(
        EVALUATION_RUNTIME,
        PLUGIN_ID,
        _default_eval_runtime,
        priority=DEFAULT_PRIORITY,
        source="default",
        is_default=True,
        is_factory=True,
    )
    registry.provide(
        TRAJECTORY_SEAL,
        PLUGIN_ID,
        _default_trajectory_seal,
        priority=DEFAULT_PRIORITY,
        source="default",
        is_default=True,
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "DefaultExecutor", "register_defaults"]
