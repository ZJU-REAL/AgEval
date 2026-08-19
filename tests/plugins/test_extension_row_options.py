"""extensions[].options is the only map a plugin factory sees."""

from __future__ import annotations

from typing import Any

from ageval.plugins.protocol import BindingIntent, ExtensionSelect, intent_from_profile
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.slots import EXECUTOR


def _factory(
    *, options: dict[str, Any] | None = None, plugin_id: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    return {"options": dict(options or {}), "plugin_id": plugin_id, "kwargs": kwargs}


def test_factory_sees_only_its_row_options() -> None:
    reg = ExtensionRegistry()
    captured: list[dict[str, Any]] = []

    def acp_factory(**kwargs: Any) -> dict[str, Any]:
        captured.append({"plugin": "acp", **_factory(**kwargs)})
        return captured[-1]

    def dsh_factory(**kwargs: Any) -> dict[str, Any]:
        captured.append({"plugin": "dsh", **_factory(**kwargs)})
        return captured[-1]

    reg.provide(EXECUTOR, "acp", acp_factory, source="first-party", is_factory=True)
    reg.provide(EXECUTOR, "dsh", dsh_factory, source="installed", is_factory=True)

    intent = intent_from_profile(
        {
            "id": "solver",
            "executor": "dsh",
            "options": {"entry": "opencode", "composition": "must-not-leak"},
            "extensions": [
                {"plugin": "acp", "options": {"entry": "opencode"}},
                {"plugin": "dsh", "options": {"composition": "slim"}},
            ],
        }
    )
    graph = resolve(intent, reg)
    impl = graph.providers[EXECUTOR].impl
    assert impl["plugin"] == "dsh"
    assert impl["options"] == {"composition": "slim"}
    assert "entry" not in impl["options"]
    assert "must-not-leak" not in str(impl["options"])


def test_profile_options_are_not_plugin_input() -> None:
    reg = ExtensionRegistry()

    def acp_factory(**kwargs: Any) -> dict[str, Any]:
        return _factory(**kwargs)

    reg.provide(EXECUTOR, "acp", acp_factory, source="first-party", is_factory=True)
    graph = resolve(
        BindingIntent(
            profile_id="s",
            executor="acp",
            options={"entry": "pi"},
            extension_selects=[ExtensionSelect(plugin="acp")],
        ),
        reg,
    )
    assert graph.providers[EXECUTOR].impl["options"] == {}
