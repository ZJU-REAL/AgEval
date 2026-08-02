"""Outer lifecycle state machine (pure transitions).

States follow Spec 01 / design Core 2. Transitions are validated *before*
appending events or facts so illegal jumps leave history untouched.
"""

from __future__ import annotations

from enum import StrEnum

from bora.runtime.errors import (
    ERROR_DUPLICATE_STAGE,
    ERROR_ILLEGAL_TRANSITION,
    ERROR_TERMINAL_REOPEN,
    LifecycleError,
)


class LifecycleState(StrEnum):
    """Outer Attempt states (Core 2)."""

    CREATED = "created"
    PREPARING = "preparing"
    RUNNING_HARNESS = "running_harness"
    HARNESS_TERMINAL = "harness_terminal"
    SEALING_INPUTS = "sealing_inputs"
    EVALUATING = "evaluating"
    BINDING_RESULT = "binding_result"
    CLEANING_UP = "cleaning_up"
    TERMINAL = "terminal"


class LifecyclePhase(StrEnum):
    """Generic stage names for phase facts (internal seam)."""

    PREPARE = "prepare"
    RUN = "run"
    SEAL = "seal"
    EVALUATE = "evaluate"
    BIND = "bind"
    CLEANUP = "cleanup"


# Success path: adjacent transitions only.
_SUCCESS_EDGES: dict[LifecycleState, LifecycleState] = {
    LifecycleState.CREATED: LifecycleState.PREPARING,
    LifecycleState.PREPARING: LifecycleState.RUNNING_HARNESS,
    LifecycleState.RUNNING_HARNESS: LifecycleState.HARNESS_TERMINAL,
    LifecycleState.HARNESS_TERMINAL: LifecycleState.SEALING_INPUTS,
    LifecycleState.SEALING_INPUTS: LifecycleState.EVALUATING,
    LifecycleState.EVALUATING: LifecycleState.BINDING_RESULT,
    LifecycleState.BINDING_RESULT: LifecycleState.CLEANING_UP,
    LifecycleState.CLEANING_UP: LifecycleState.TERMINAL,
}

# States that may enter cleanup early on failure/cancel/timeout.
_EARLY_CLEANUP_SOURCES = frozenset(
    {
        LifecycleState.CREATED,
        LifecycleState.PREPARING,
        LifecycleState.RUNNING_HARNESS,
        LifecycleState.HARNESS_TERMINAL,
        LifecycleState.SEALING_INPUTS,
        LifecycleState.EVALUATING,
        LifecycleState.BINDING_RESULT,
    }
)

# Map success-path state to the stage that must complete before leaving it.
STATE_TO_PHASE: dict[LifecycleState, LifecyclePhase] = {
    LifecycleState.PREPARING: LifecyclePhase.PREPARE,
    LifecycleState.RUNNING_HARNESS: LifecyclePhase.RUN,
    LifecycleState.SEALING_INPUTS: LifecyclePhase.SEAL,
    LifecycleState.EVALUATING: LifecyclePhase.EVALUATE,
    LifecycleState.BINDING_RESULT: LifecyclePhase.BIND,
    LifecycleState.CLEANING_UP: LifecyclePhase.CLEANUP,
}


def allowed_success_target(current: LifecycleState) -> LifecycleState | None:
    """Return the only allowed success successor, or None if terminal."""
    return _SUCCESS_EDGES.get(current)


def validate_transition(
    current: LifecycleState,
    target: LifecycleState,
    *,
    reason: str = "success",
) -> None:
    """Validate a transition before mutating the aggregate.

    Parameters
    ----------
    reason:
        ``success`` for the happy path; ``failure`` / ``cancelled`` / ``timed_out``
        allow early entry into ``cleaning_up`` from non-terminal states.
        ``cleanup_done`` is used only for ``cleaning_up → terminal``.
    """
    if current == LifecycleState.TERMINAL:
        raise LifecycleError(
            ERROR_TERMINAL_REOPEN,
            f"cannot leave terminal state toward {target.value}",
        )

    if reason == "success":
        expected = _SUCCESS_EDGES.get(current)
        if expected is None or target != expected:
            raise LifecycleError(
                ERROR_ILLEGAL_TRANSITION,
                f"illegal success transition {current.value} → {target.value}",
            )
        return

    if reason == "cleanup_done":
        if current != LifecycleState.CLEANING_UP or target != LifecycleState.TERMINAL:
            raise LifecycleError(
                ERROR_ILLEGAL_TRANSITION,
                f"illegal cleanup completion {current.value} → {target.value}",
            )
        return

    # Early cleanup for failure / cancel / timeout.
    if target != LifecycleState.CLEANING_UP:
        raise LifecycleError(
            ERROR_ILLEGAL_TRANSITION,
            f"early exit must enter cleaning_up, not {target.value}",
        )
    if current not in _EARLY_CLEANUP_SOURCES:
        raise LifecycleError(
            ERROR_ILLEGAL_TRANSITION,
            f"cannot enter cleaning_up from {current.value}",
        )
    if current == LifecycleState.CLEANING_UP:
        raise LifecycleError(
            ERROR_DUPLICATE_STAGE,
            "cleanup already in progress",
        )


def success_path() -> tuple[LifecycleState, ...]:
    """Ordered success-path states including terminal."""
    return (
        LifecycleState.CREATED,
        LifecycleState.PREPARING,
        LifecycleState.RUNNING_HARNESS,
        LifecycleState.HARNESS_TERMINAL,
        LifecycleState.SEALING_INPUTS,
        LifecycleState.EVALUATING,
        LifecycleState.BINDING_RESULT,
        LifecycleState.CLEANING_UP,
        LifecycleState.TERMINAL,
    )
