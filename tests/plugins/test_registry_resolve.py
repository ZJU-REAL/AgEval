"""Spec 00 unit tests: registry, conflict, resolve, lock_bind, multi chain order."""

from __future__ import annotations

import asyncio

import pytest

from bora.plugins.conflict import ExtensionConflictError
from bora.plugins.defaults import register_defaults
from bora.plugins.errors import ExtensionPluginNotFoundError, UnknownExtensionSlotError
from bora.plugins.lock_bind import extension_graph_to_lock
from bora.plugins.middleware import run_chain
from bora.plugins.protocol import BindingIntent, ExplicitBinding
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.resolve import resolve
from bora.plugins.slots import BEFORE_AGENT_INVOKE, EXECUTOR


class _FakeExec:
    kind = "fake"

    def open(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs

    def close(self) -> None:
        return None

    def invoke(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"ok": True, "text": prompt, "model": "fake"}


def test_defaults_do_not_provide_executor() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    graph = resolve(BindingIntent(profile_id="solver"), reg)
    assert EXECUTOR not in graph.providers


def test_explicit_binding_overrides_lower_priority() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    reg.provide(EXECUTOR, "low", _FakeExec(), priority=200, source="installed")
    reg.provide(EXECUTOR, "winner", _FakeExec(), priority=50, source="installed")
    intent = BindingIntent(
        profile_id="solver",
        extensions=[ExplicitBinding(slot=EXECUTOR, plugin="winner", source="explicit")],
    )
    graph = resolve(intent, reg)
    assert graph.providers[EXECUTOR].plugin_id == "winner"
    assert graph.providers[EXECUTOR].source == "explicit"


def test_priority_tie_without_explicit_fail_closed() -> None:
    reg = ExtensionRegistry()
    reg.provide(EXECUTOR, "a", _FakeExec(), priority=10, source="installed")
    reg.provide(EXECUTOR, "b", _FakeExec(), priority=10, source="installed")
    with pytest.raises(ExtensionConflictError) as ei:
        resolve(BindingIntent(profile_id="s"), reg)
    assert ei.value.kind == "extension_conflict"


def test_two_intents_do_not_pollute() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    reg.provide(EXECUTOR, "nooa", _FakeExec(), priority=10, source="first-party")
    reg.provide(EXECUTOR, "acp", _FakeExec(), priority=10, source="first-party")
    g1 = resolve(BindingIntent(profile_id="solver", executor="nooa"), reg)
    g2 = resolve(BindingIntent(profile_id="user", executor="acp"), reg)
    assert g1.providers[EXECUTOR].plugin_id == "nooa"
    assert g2.providers[EXECUTOR].plugin_id == "acp"
    assert g1.profile_id == "solver"
    assert g2.profile_id == "user"


def test_lock_bind_includes_source_priority_replaced_default() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    reg.provide(EXECUTOR, "acp", _FakeExec(), priority=100, source="first-party")
    graph = resolve(BindingIntent(profile_id="solver", executor="acp"), reg)
    frag = extension_graph_to_lock(graph)
    row = frag["executor"]
    assert row["kind"] == "provide"
    assert row["plugin"] == "acp"
    assert row["source"] == "profile_executor_field"
    assert "priority" in row
    assert frag[BEFORE_AGENT_INVOKE]["kind"] == "on"
    assert frag[BEFORE_AGENT_INVOKE]["chain"][0]["plugin"] == "default"


def test_multi_chain_order_lower_priority_number_first() -> None:
    reg = ExtensionRegistry()
    order: list[str] = []

    def make(name: str, prio: int) -> None:
        async def handler(ctx, value, nxt):  # type: ignore[no-untyped-def]
            order.append(f"enter:{name}")
            out = await nxt(value)
            order.append(f"leave:{name}")
            return out

        reg.on(BEFORE_AGENT_INVOKE, name, handler, priority=prio, source="installed")

    make("late", 100)
    make("early", 10)
    graph = resolve(BindingIntent(profile_id="s"), reg)
    result = asyncio.run(run_chain(graph, BEFORE_AGENT_INVOKE, "prompt"))
    assert result == "prompt"
    assert order[0] == "enter:early"
    assert "enter:late" in order


def test_unknown_slot_fail_closed() -> None:
    reg = ExtensionRegistry()
    with pytest.raises(UnknownExtensionSlotError):
        reg.provide("not_a_slot", "x", object())


def test_executor_field_plugin_not_registered_fail_closed() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    with pytest.raises(ExtensionPluginNotFoundError) as ei:
        resolve(BindingIntent(profile_id="s", executor="missing-plugin"), reg)
    assert ei.value.kind == "extension_plugin_not_found"


def test_profile_executor_field_selects_plugin() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    reg.provide(EXECUTOR, "acp", _FakeExec(), priority=100, source="first-party")
    graph = resolve(
        BindingIntent(profile_id="solver", executor="acp", options={"entry": "pi"}),
        reg,
    )
    assert graph.providers[EXECUTOR].plugin_id == "acp"
    assert graph.providers[EXECUTOR].source == "profile_executor_field"
