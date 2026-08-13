"""L0–L5 public extension slot ids and kind (multi chain vs single provide).

Slot name strings may evolve with aliases; the layered map is stable.
Unknown slots fail closed at resolve time.

Production consumers (#71 — host **awaits** handlers / SPI methods; no command-DSL):

- L0 ``before/after_*`` phase bookends → ``application/extension_hooks``
- L1 ``image_contribute`` → bake path
- L1 env multi/provide → env prepare/teardown + optional action gate
- L2 ``executor`` + agent open/invoke/close/normalize → ``ParentAgentService``
- L3 evaluation input/runtime/score → pre/post evaluator (fail closed)
- L4 trajectory collect/enrich/seal + evidence_extra → seal write path
- L5 cleanup_actions/report → ``emit_cleanup``

Anti-pattern: plugins must not append free-form ``{kind: shell, argv: …}``
rows for Core to interpret later — handlers run real code with live
``ctx`` + ``next``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SlotKind(StrEnum):
    """Contribution cardinality for a slot."""

    MULTI = "multi"  # ordered chain of handlers (middleware next)
    PROVIDE = "provide"  # single winner


# --- L0: attempt / phase bookends (multi) ---
BEFORE_PREPARE: Final = "before_prepare"
AFTER_PREPARE: Final = "after_prepare"
BEFORE_RUN: Final = "before_run"
AFTER_RUN: Final = "after_run"
BEFORE_EVALUATE: Final = "before_evaluate"
AFTER_EVALUATE: Final = "after_evaluate"
BEFORE_CLEANUP: Final = "before_cleanup"
AFTER_CLEANUP: Final = "after_cleanup"

# --- L1: environment / image (mostly multi merge; env_action single) ---
IMAGE_CONTRIBUTE: Final = "image_contribute"
ENV_PREPARE_COMMANDS: Final = "env_prepare_commands"
ENV_INJECT: Final = "env_inject"
ENV_ACTION: Final = "env_action"
ENV_TEARDOWN_COMMANDS: Final = "env_teardown_commands"

# --- L2: agent executor + session hooks ---
EXECUTOR: Final = "executor"
BEFORE_AGENT_OPEN: Final = "before_agent_open"
AFTER_AGENT_OPEN: Final = "after_agent_open"
BEFORE_AGENT_INVOKE: Final = "before_agent_invoke"
AFTER_AGENT_INVOKE: Final = "after_agent_invoke"
BEFORE_AGENT_CLOSE: Final = "before_agent_close"
AFTER_AGENT_CLOSE: Final = "after_agent_close"
NORMALIZE_AGENT_RESULT: Final = "normalize_agent_result"

# --- L3: evaluation adjacency ---
EVALUATION_INPUT_CONTRIBUTE: Final = "evaluation_input_contribute"
EVALUATION_RUNTIME: Final = "evaluation_runtime"
SCORE_POSTPROCESS: Final = "score_postprocess"

# --- L4: trajectory / evidence ---
TRAJECTORY_COLLECT: Final = "trajectory_collect"
TRAJECTORY_ENRICH: Final = "trajectory_enrich"
TRAJECTORY_SEAL: Final = "trajectory_seal"
EVIDENCE_EXTRA: Final = "evidence_extra"

# --- L5: cleanup ---
CLEANUP_ACTIONS: Final = "cleanup_actions"
CLEANUP_REPORT: Final = "cleanup_report"

# Default numeric priority for builtin contributions (higher number = later / weaker).
# Convention: **lower number runs first** (multi) and **wins** (provide) when no explicit.
DEFAULT_PRIORITY: Final = 1000

_SLOT_KINDS: Final[dict[str, SlotKind]] = {
    # L0
    BEFORE_PREPARE: SlotKind.MULTI,
    AFTER_PREPARE: SlotKind.MULTI,
    BEFORE_RUN: SlotKind.MULTI,
    AFTER_RUN: SlotKind.MULTI,
    BEFORE_EVALUATE: SlotKind.MULTI,
    AFTER_EVALUATE: SlotKind.MULTI,
    BEFORE_CLEANUP: SlotKind.MULTI,
    AFTER_CLEANUP: SlotKind.MULTI,
    # L1
    IMAGE_CONTRIBUTE: SlotKind.MULTI,
    ENV_PREPARE_COMMANDS: SlotKind.MULTI,
    ENV_INJECT: SlotKind.MULTI,
    ENV_ACTION: SlotKind.PROVIDE,
    ENV_TEARDOWN_COMMANDS: SlotKind.MULTI,
    # L2
    EXECUTOR: SlotKind.PROVIDE,
    BEFORE_AGENT_OPEN: SlotKind.MULTI,
    AFTER_AGENT_OPEN: SlotKind.MULTI,
    BEFORE_AGENT_INVOKE: SlotKind.MULTI,
    AFTER_AGENT_INVOKE: SlotKind.MULTI,
    BEFORE_AGENT_CLOSE: SlotKind.MULTI,
    AFTER_AGENT_CLOSE: SlotKind.MULTI,
    NORMALIZE_AGENT_RESULT: SlotKind.MULTI,
    # L3
    EVALUATION_INPUT_CONTRIBUTE: SlotKind.MULTI,
    EVALUATION_RUNTIME: SlotKind.PROVIDE,
    SCORE_POSTPROCESS: SlotKind.MULTI,
    # L4
    TRAJECTORY_COLLECT: SlotKind.MULTI,
    TRAJECTORY_ENRICH: SlotKind.MULTI,
    TRAJECTORY_SEAL: SlotKind.PROVIDE,
    EVIDENCE_EXTRA: SlotKind.MULTI,
    # L5
    CLEANUP_ACTIONS: SlotKind.MULTI,
    CLEANUP_REPORT: SlotKind.MULTI,
}

ALL_PUBLIC_SLOTS: Final[tuple[str, ...]] = tuple(_SLOT_KINDS.keys())

# Declared-slot timeline layers (Hub plugin detail). Stable with the comments above.
SLOT_LEVEL: Final[dict[str, int]] = {
    BEFORE_PREPARE: 0,
    AFTER_PREPARE: 0,
    BEFORE_RUN: 0,
    AFTER_RUN: 0,
    BEFORE_EVALUATE: 0,
    AFTER_EVALUATE: 0,
    BEFORE_CLEANUP: 0,
    AFTER_CLEANUP: 0,
    IMAGE_CONTRIBUTE: 1,
    ENV_PREPARE_COMMANDS: 1,
    ENV_INJECT: 1,
    ENV_ACTION: 1,
    ENV_TEARDOWN_COMMANDS: 1,
    EXECUTOR: 2,
    BEFORE_AGENT_OPEN: 2,
    AFTER_AGENT_OPEN: 2,
    BEFORE_AGENT_INVOKE: 2,
    AFTER_AGENT_INVOKE: 2,
    BEFORE_AGENT_CLOSE: 2,
    AFTER_AGENT_CLOSE: 2,
    NORMALIZE_AGENT_RESULT: 2,
    EVALUATION_INPUT_CONTRIBUTE: 3,
    EVALUATION_RUNTIME: 3,
    SCORE_POSTPROCESS: 3,
    TRAJECTORY_COLLECT: 4,
    TRAJECTORY_ENRICH: 4,
    TRAJECTORY_SEAL: 4,
    EVIDENCE_EXTRA: 4,
    CLEANUP_ACTIONS: 5,
    CLEANUP_REPORT: 5,
}

LEVEL_LABELS: Final[tuple[str, ...]] = (
    "Attempt / phase bookends",
    "Environment and image",
    "Agent executor and session",
    "Evaluation adjacency",
    "Trajectory and evidence",
    "Cleanup",
)


def slot_level(slot: str) -> int | None:
    """L0–L5 index for a public slot id, or None if unknown."""
    return SLOT_LEVEL.get(slot)


def is_public_slot(slot: str) -> bool:
    return slot in _SLOT_KINDS


def get_slot_kind(slot: str) -> SlotKind:
    if slot not in _SLOT_KINDS:
        from bora.plugins.errors import UnknownExtensionSlotError

        raise UnknownExtensionSlotError(
            f"unknown extension slot: {slot!r}",
            kind="unknown_extension_slot",
        )
    return _SLOT_KINDS[slot]
