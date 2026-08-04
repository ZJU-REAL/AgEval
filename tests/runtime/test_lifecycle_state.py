"""Pure state transition table tests."""

from __future__ import annotations

import pytest

from bora.runtime.errors import LifecycleError
from bora.runtime.lifecycle import LifecycleState, success_path, validate_transition


def test_success_path_adjacent() -> None:
    path = success_path()
    for a, b in zip(path, path[1:], strict=False):
        validate_transition(a, b, reason="success")


def test_illegal_jump() -> None:
    with pytest.raises(LifecycleError) as ei:
        validate_transition(LifecycleState.CREATED, LifecycleState.EVALUATING, reason="success")
    assert ei.value.error_code == "illegal_transition"


def test_terminal_reopen() -> None:
    with pytest.raises(LifecycleError) as ei:
        validate_transition(LifecycleState.TERMINAL, LifecycleState.CREATED, reason="success")
    assert ei.value.error_code == "terminal_reopen"


def test_early_cleanup_from_running() -> None:
    validate_transition(
        LifecycleState.RUNNING_HARNESS,
        LifecycleState.CLEANING_UP,
        reason="failure",
    )


def test_cleanup_to_terminal() -> None:
    validate_transition(
        LifecycleState.CLEANING_UP,
        LifecycleState.TERMINAL,
        reason="cleanup_done",
    )
