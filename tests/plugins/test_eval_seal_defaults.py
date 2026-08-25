"""Engine defaults win evaluation_runtime and trajectory_seal; lock fails closed without them."""

from __future__ import annotations

import pytest

from ageval.plugins.defaults import PLUGIN_ID, register_defaults
from ageval.plugins.errors import ExtensionPluginNotFoundError
from ageval.plugins.protocol import BindingIntent
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import _SUGAR_SLOTS, resolve
from ageval.plugins.services import RESERVED_SERVICE_IDS
from ageval.plugins.slots import (
    EVALUATION_RUNTIME,
    FAIL_OPEN_SLOTS,
    SUMMARY_ENRICH,
    TRAJECTORY_SEAL,
)


def test_sugar_slots_do_not_include_eval_or_seal() -> None:
    assert EVALUATION_RUNTIME not in _SUGAR_SLOTS
    assert TRAJECTORY_SEAL not in _SUGAR_SLOTS


def test_eval_and_seal_are_fail_closed() -> None:
    assert EVALUATION_RUNTIME not in FAIL_OPEN_SLOTS
    assert TRAJECTORY_SEAL not in FAIL_OPEN_SLOTS
    assert SUMMARY_ENRICH in FAIL_OPEN_SLOTS


def test_reserved_services_still_block_pass_identity_cleanup_evidence() -> None:
    from ageval.plugins.errors import ServiceConflictError
    from ageval.plugins.services import ServiceTable

    assert frozenset({"pass", "identity", "cleanup", "evidence"}) == RESERVED_SERVICE_IDS
    registry = ExtensionRegistry()
    table = ServiceTable()
    for name in RESERVED_SERVICE_IDS:
        with pytest.raises(ServiceConflictError, match="engine invariant"):
            registry.export_service(name, "probe", object())
        with pytest.raises(ServiceConflictError, match="engine invariant"):
            table.register(name, object(), plugin_id="probe")


def test_defaults_win_eval_and_seal_without_explicit_row() -> None:
    registry = ExtensionRegistry()
    register_defaults(registry)
    graph = resolve(BindingIntent(profile_id="solver"), registry)
    runtime = graph.winners[EVALUATION_RUNTIME]
    assert runtime.plugin_id == PLUGIN_ID
    assert runtime.source == "default"
    seal = graph.winners[TRAJECTORY_SEAL]
    assert seal.plugin_id == PLUGIN_ID
    assert seal.source == "default"
    assert graph.services[EVALUATION_RUNTIME] == PLUGIN_ID
    assert graph.services[TRAJECTORY_SEAL] == PLUGIN_ID


def test_missing_default_registration_fails_closed() -> None:
    registry = ExtensionRegistry()
    with pytest.raises(ExtensionPluginNotFoundError, match="evaluation_runtime"):
        resolve(BindingIntent(profile_id="solver"), registry)
