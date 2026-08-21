"""What a plugin factory sees: the profile's options, then its own row on top.

The profile is where a job names its entry, so the winner reads it. Another
plugin's row is still none of its business.
"""

from __future__ import annotations

from typing import Any

from ageval.plugins.binding import bind_winner
from ageval.plugins.defaults import register_defaults
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
    register_defaults(reg)
    captured: list[dict[str, Any]] = []

    def acp_factory(**kwargs: Any) -> dict[str, Any]:
        captured.append({"plugin": "acp", **_factory(**kwargs)})
        return captured[-1]

    def dsh_factory(**kwargs: Any) -> dict[str, Any]:
        captured.append({"plugin": "dsh", **_factory(**kwargs)})
        return captured[-1]

    reg.exclusive(EXECUTOR, "acp", acp_factory, source="first-party", is_factory=True)
    reg.exclusive(EXECUTOR, "dsh", dsh_factory, source="installed", is_factory=True)

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
    impl = bind_winner(reg, graph, EXECUTOR)
    assert impl["plugin"] == "dsh"
    # The row wins over the profile for the same key, and the profile's own
    # entry reaches the winner because that is where a job declares it.
    assert impl["options"] == {"entry": "opencode", "composition": "slim"}
    assert "must-not-leak" not in str(impl["options"])


def test_profile_options_reach_the_winner() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)

    def acp_factory(**kwargs: Any) -> dict[str, Any]:
        return _factory(**kwargs)

    reg.exclusive(EXECUTOR, "acp", acp_factory, source="first-party", is_factory=True)
    graph = resolve(
        BindingIntent(
            profile_id="s",
            executor="acp",
            options={"entry": "pi"},
            extension_selects=[ExtensionSelect(plugin="acp")],
        ),
        reg,
    )
    assert bind_winner(reg, graph, EXECUTOR)["options"] == {"entry": "pi"}
