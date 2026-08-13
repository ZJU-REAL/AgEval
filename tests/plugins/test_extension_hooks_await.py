"""Spec 05 Phase 1: lifecycle hooks always await; prepare can fail closed."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from bora.application.attempt import extension_hooks as hooks
from bora.plugins.protocol import BindingIntent, ExtensionGraph


def _fake_lock() -> Any:
    return SimpleNamespace(agent_profiles=[])


def test_run_awaits_without_running_loop() -> None:
    calls: list[str] = []

    async def _coro() -> str:
        calls.append("ran")
        return "ok"

    assert hooks._run(_coro()) == "ok"
    assert calls == ["ran"]


def test_run_awaits_inside_running_loop() -> None:
    calls: list[str] = []

    async def _coro() -> str:
        calls.append("nested")
        return "nested-ok"

    async def _outer() -> str:
        return hooks._run(_coro())

    assert asyncio.run(_outer()) == "nested-ok"
    assert calls == ["nested"]


def test_hook_prepare_invokes_emit_and_returns() -> None:
    counter = {"n": 0}

    async def fake_emit(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
        del graph, ctx
        counter["n"] += 1
        return value if value is not None else {"prepared": True}

    lock = _fake_lock()
    with (
        patch.object(hooks, "graph_for_lock", return_value=ExtensionGraph(profile_id="t")),
        patch.object(hooks, "emit_prepare", side_effect=fake_emit),
    ):
        out = hooks.hook_prepare(lock, {"seed": 1})
    assert counter["n"] == 1
    assert out == {"seed": 1}


def test_hook_prepare_fail_closed_raises() -> None:
    async def boom(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
        del graph, value, ctx
        raise RuntimeError("prepare_bake_failed")

    lock = _fake_lock()
    with (
        patch.object(hooks, "graph_for_lock", return_value=ExtensionGraph(profile_id="t")),
        patch.object(hooks, "emit_prepare", side_effect=boom),
        pytest.raises(RuntimeError, match="prepare_bake_failed"),
    ):
        hooks.hook_prepare(lock, fail_closed=True)


def test_hook_prepare_fail_open_returns_value() -> None:
    async def boom(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
        del graph, ctx
        raise RuntimeError("soft")

    lock = _fake_lock()
    with (
        patch.object(hooks, "graph_for_lock", return_value=ExtensionGraph(profile_id="t")),
        patch.object(hooks, "emit_prepare", side_effect=boom),
    ):
        assert hooks.hook_prepare(lock, "keep", fail_closed=False) == "keep"


def test_hook_run_fail_open_on_error() -> None:
    async def boom(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
        del graph, ctx
        raise RuntimeError("run_hook")

    lock = _fake_lock()
    with (
        patch.object(hooks, "graph_for_lock", return_value=ExtensionGraph(profile_id="t")),
        patch.object(hooks, "emit_run", side_effect=boom),
    ):
        assert hooks.hook_run(lock, "v") == "v"


def test_graph_for_lock_empty_profiles_resolves() -> None:
    from bora.plugins.bootstrap import ensure_bootstrapped

    ensure_bootstrapped()
    g = hooks.graph_for_lock(_fake_lock())
    assert isinstance(g, ExtensionGraph)
    assert g.profile_id == "_lifecycle"


def test_intent_import_still_available() -> None:
    # Sanity: BindingIntent used by graph_for_lock path.
    assert BindingIntent(profile_id="x").profile_id == "x"
