"""Slot vocabulary owned by the Attempt host.

Two kinds only:

* **exclusive** — one winner for the whole Attempt; the winner is registered as
  a service under the same name so other plugins can ``inject`` it.
* **chain** — ordered handlers ``(ctx, value, nxt)`` inside one phase.

Slot names are the host's vocabulary: a plugin may fill a slot, never invent
one. Adding a timeline slot means editing this file *and* the phase that emits
it (``ageval/attempt/phases/*``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SlotKind(StrEnum):
    EXCLUSIVE = "exclusive"
    CHAIN = "chain"


# --- exclusive slots (winner is also a service) ---
ENVIRONMENT: Final = "environment"
EXECUTOR: Final = "executor"
EVALUATION_RUNTIME: Final = "evaluation_runtime"
TRAJECTORY_SEAL: Final = "trajectory_seal"

# --- environment phase chain ---
BEFORE_ENVIRONMENT: Final = "before_environment"
AFTER_ENVIRONMENT_READY: Final = "after_environment_ready"
ENVIRONMENT_SETUP: Final = "environment_setup"
AFTER_ENVIRONMENT: Final = "after_environment"

# --- run phase chain ---
BEFORE_RUN: Final = "before_run"
AFTER_RUN: Final = "after_run"
BEFORE_AGENT_OPEN: Final = "before_agent_open"
AFTER_AGENT_OPEN: Final = "after_agent_open"
BEFORE_AGENT_INVOKE: Final = "before_agent_invoke"
AFTER_AGENT_INVOKE: Final = "after_agent_invoke"
BEFORE_AGENT_CLOSE: Final = "before_agent_close"
AFTER_AGENT_CLOSE: Final = "after_agent_close"
NORMALIZE_AGENT_RESULT: Final = "normalize_agent_result"

# --- evaluate phase chain ---
BEFORE_EVALUATE: Final = "before_evaluate"
AFTER_EVALUATE: Final = "after_evaluate"

# --- record phase chain ---
TRAJECTORY_COLLECT: Final = "trajectory_collect"
TRAJECTORY_ENRICH: Final = "trajectory_enrich"

# --- cleanup phase chain ---
CLEANUP_REPORT: Final = "cleanup_report"

# Lower number runs first in a chain and wins an exclusive slot.
DEFAULT_PRIORITY: Final = 1000

_SLOT_KINDS: Final[dict[str, SlotKind]] = {
    ENVIRONMENT: SlotKind.EXCLUSIVE,
    EXECUTOR: SlotKind.EXCLUSIVE,
    EVALUATION_RUNTIME: SlotKind.EXCLUSIVE,
    TRAJECTORY_SEAL: SlotKind.EXCLUSIVE,
    BEFORE_ENVIRONMENT: SlotKind.CHAIN,
    AFTER_ENVIRONMENT_READY: SlotKind.CHAIN,
    ENVIRONMENT_SETUP: SlotKind.CHAIN,
    AFTER_ENVIRONMENT: SlotKind.CHAIN,
    BEFORE_RUN: SlotKind.CHAIN,
    AFTER_RUN: SlotKind.CHAIN,
    BEFORE_AGENT_OPEN: SlotKind.CHAIN,
    AFTER_AGENT_OPEN: SlotKind.CHAIN,
    BEFORE_AGENT_INVOKE: SlotKind.CHAIN,
    AFTER_AGENT_INVOKE: SlotKind.CHAIN,
    BEFORE_AGENT_CLOSE: SlotKind.CHAIN,
    AFTER_AGENT_CLOSE: SlotKind.CHAIN,
    NORMALIZE_AGENT_RESULT: SlotKind.CHAIN,
    BEFORE_EVALUATE: SlotKind.CHAIN,
    AFTER_EVALUATE: SlotKind.CHAIN,
    TRAJECTORY_COLLECT: SlotKind.CHAIN,
    TRAJECTORY_ENRICH: SlotKind.CHAIN,
    CLEANUP_REPORT: SlotKind.CHAIN,
}

ALL_SLOTS: Final[tuple[str, ...]] = tuple(_SLOT_KINDS)
EXCLUSIVE_SLOTS: Final[tuple[str, ...]] = tuple(
    s for s, k in _SLOT_KINDS.items() if k is SlotKind.EXCLUSIVE
)

# Must have a winner at lock even with no job field. ``environment`` /
# ``executor`` are selected by sugar; these two are engine defaults.
REQUIRED_EXCLUSIVE_SLOTS: Final[frozenset[str]] = frozenset(
    {EVALUATION_RUNTIME, TRAJECTORY_SEAL}
)

# Chain slots whose handler failure is recorded and stepped over. Everything
# else fails its phase.
FAIL_OPEN_SLOTS: Final[frozenset[str]] = frozenset(
    {
        BEFORE_RUN,
        AFTER_RUN,
        TRAJECTORY_COLLECT,
        TRAJECTORY_ENRICH,
        CLEANUP_REPORT,
    }
)


def is_slot(slot: str) -> bool:
    return slot in _SLOT_KINDS


def get_slot_kind(slot: str) -> SlotKind:
    if slot not in _SLOT_KINDS:
        from ageval.plugins.errors import UnknownExtensionSlotError

        raise UnknownExtensionSlotError(
            f"unknown extension slot: {slot!r}",
            kind="unknown_extension_slot",
        )
    return _SLOT_KINDS[slot]


def is_fail_open(slot: str) -> bool:
    return slot in FAIL_OPEN_SLOTS
