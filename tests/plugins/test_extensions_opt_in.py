"""extensions opt-in: installed plugins stay off MULTI unless named."""

from __future__ import annotations

import pytest

from bora.plugins.defaults import register_defaults
from bora.plugins.errors import ExtensionPluginNotFoundError, UnknownExtensionSlotError
from bora.plugins.protocol import BindingIntent, ExtensionSelect, intent_from_profile
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.resolve import resolve
from bora.plugins.slots import EXECUTOR, IMAGE_CONTRIBUTE, TRAJECTORY_COLLECT


class _FakeExec:
    kind = "fake"

    def open(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs

    def close(self) -> None:
        return None

    def invoke(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"ok": True, "text": prompt}


async def _passthrough(ctx, value, nxt):  # type: ignore[no-untyped-def]
    del ctx
    return await nxt(value)


def _reg_with_external() -> ExtensionRegistry:
    reg = ExtensionRegistry()
    register_defaults(reg)
    reg.provide(EXECUTOR, "acp", _FakeExec(), priority=100, source="first-party")
    reg.provide(EXECUTOR, "nooa", _FakeExec(), priority=110, source="installed")
    reg.on(IMAGE_CONTRIBUTE, "nooa", _passthrough, priority=110, source="installed")
    reg.on(TRAJECTORY_COLLECT, "nooa", _passthrough, priority=110, source="installed")
    reg.provide(EXECUTOR, "dsh", _FakeExec(), priority=110, source="installed")
    reg.on(IMAGE_CONTRIBUTE, "dsh", _passthrough, priority=110, source="installed")
    reg.on(TRAJECTORY_COLLECT, "dsh", _passthrough, priority=110, source="installed")
    return reg


def _chain_plugins(graph, slot: str) -> list[str]:
    return [h.plugin_id for h in graph.chain(slot)]


def test_acp_only_does_not_attach_installed_contribute() -> None:
    graph = resolve(BindingIntent(profile_id="solver", executor="acp"), _reg_with_external())
    assert graph.providers[EXECUTOR].plugin_id == "acp"
    assert "nooa" not in _chain_plugins(graph, IMAGE_CONTRIBUTE)
    assert "dsh" not in _chain_plugins(graph, IMAGE_CONTRIBUTE)
    assert "nooa" not in _chain_plugins(graph, TRAJECTORY_COLLECT)
    assert "dsh" not in _chain_plugins(graph, TRAJECTORY_COLLECT)


def test_all_slots_row_attaches_bake_and_collect() -> None:
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            executor="nooa",
            extension_selects=[ExtensionSelect(plugin="nooa")],
        ),
        _reg_with_external(),
    )
    assert graph.providers[EXECUTOR].plugin_id == "nooa"
    assert "nooa" in _chain_plugins(graph, IMAGE_CONTRIBUTE)
    assert "nooa" in _chain_plugins(graph, TRAJECTORY_COLLECT)
    assert "dsh" not in _chain_plugins(graph, IMAGE_CONTRIBUTE)


def test_listed_slots_do_not_attach_unlisted() -> None:
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            executor="dsh",
            extension_selects=[
                ExtensionSelect(plugin="dsh", slots=(IMAGE_CONTRIBUTE,)),
            ],
        ),
        _reg_with_external(),
    )
    assert "dsh" in _chain_plugins(graph, IMAGE_CONTRIBUTE)
    assert "dsh" not in _chain_plugins(graph, TRAJECTORY_COLLECT)


def test_unknown_slot_fail_closed() -> None:
    with pytest.raises(UnknownExtensionSlotError):
        resolve(
            BindingIntent(
                profile_id="s",
                extension_selects=[ExtensionSelect(plugin="dsh", slots=("not_a_slot",))],
            ),
            _reg_with_external(),
        )


def test_unregistered_slot_fail_closed() -> None:
    with pytest.raises(ExtensionPluginNotFoundError) as ei:
        resolve(
            BindingIntent(
                profile_id="s",
                extension_selects=[
                    ExtensionSelect(plugin="dsh", slots=("before_agent_invoke",)),
                ],
            ),
            _reg_with_external(),
        )
    assert ei.value.kind == "extension_slot_unregistered"


def test_two_roles_bind_independently() -> None:
    reg = _reg_with_external()
    planner = resolve(
        BindingIntent(
            profile_id="planner",
            executor="nooa",
            extension_selects=[ExtensionSelect(plugin="nooa")],
        ),
        reg,
    )
    reviewer = resolve(
        BindingIntent(
            profile_id="reviewer",
            executor="dsh",
            extension_selects=[ExtensionSelect(plugin="dsh", slots=(IMAGE_CONTRIBUTE,))],
        ),
        reg,
    )
    assert planner.providers[EXECUTOR].plugin_id == "nooa"
    assert reviewer.providers[EXECUTOR].plugin_id == "dsh"
    assert "nooa" in _chain_plugins(planner, TRAJECTORY_COLLECT)
    assert "dsh" not in _chain_plugins(reviewer, TRAJECTORY_COLLECT)
    assert "dsh" in _chain_plugins(reviewer, IMAGE_CONTRIBUTE)
    assert "nooa" not in _chain_plugins(reviewer, IMAGE_CONTRIBUTE)


def test_executor_field_alone_does_not_bake() -> None:
    graph = resolve(
        BindingIntent(profile_id="solver", executor="nooa"),
        _reg_with_external(),
    )
    assert graph.providers[EXECUTOR].plugin_id == "nooa"
    assert "nooa" not in _chain_plugins(graph, IMAGE_CONTRIBUTE)


def test_all_slots_row_can_omit_executor_field() -> None:
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extension_selects=[ExtensionSelect(plugin="nooa")],
        ),
        _reg_with_external(),
    )
    assert graph.providers[EXECUTOR].plugin_id == "nooa"


def test_intent_from_profile_parses_all_three_shapes() -> None:
    intent = intent_from_profile(
        {
            "id": "solver",
            "executor": "dsh",
            "extensions": [
                {"plugin": "nooa"},
                {"plugin": "dsh", "slots": ["image_contribute"]},
                {"slot": "trajectory_collect", "plugin": "dsh"},
            ],
        }
    )
    assert intent.executor == "dsh"
    assert len(intent.extension_selects) == 2
    assert intent.extension_selects[0].plugin == "nooa"
    assert intent.extension_selects[0].slots is None
    assert intent.extension_selects[1].slots == (IMAGE_CONTRIBUTE,)
    assert len(intent.extensions) == 1
    assert intent.extensions[0].slot == TRAJECTORY_COLLECT
    assert intent.extensions[0].plugin == "dsh"
