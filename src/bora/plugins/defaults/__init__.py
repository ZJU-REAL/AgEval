"""Builtin default contributions for L0–L5 multi hooks and non-executor provides.

MVP: **no** default executor that bridges ``agent_registry.resolve_executor``.
Executor comes from first-party contribs (acp, …) or installed plugins
(e.g. nooa via ``bora plugin install``), selected by profiles ``executor:``
field. Defaults cover chain slots + seal/env/eval stubs.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.defaults.home_overlay import HOME_OVERLAY_PRIORITY, default_home_overlay
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
    HOME_OVERLAY,
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


def _default_eval_runtime(**_kwargs: Any) -> dict[str, Any]:
    return {"runtime": "package", "source": "default"}


def _default_trajectory_seal(**_kwargs: Any) -> dict[str, Any]:
    """Authority shape marker — actual seal stays in evidence store path."""
    return {"seal": "default_authority_shape", "plugin": PLUGIN_ID}


def _default_env_action(**_kwargs: Any) -> dict[str, Any]:
    return {"action": "default_deny_unknown", "plugin": PLUGIN_ID}


def register_defaults(registry: ExtensionRegistry) -> None:
    """Register default multi handlers + non-executor provides for every public layer."""
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
    registry.on(
        HOME_OVERLAY,
        PLUGIN_ID,
        default_home_overlay,
        priority=HOME_OVERLAY_PRIORITY,
        source="default",
        is_default=True,
        is_factory=False,
    )
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


__all__ = ["PLUGIN_ID", "register_defaults"]
