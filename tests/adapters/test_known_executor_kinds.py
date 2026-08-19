"""Known executor kinds come from the registry, not a second hardcoded list."""

from __future__ import annotations

from ageval.plugins.contrib.acp.path_probe import probe_commands
from ageval.plugins.executor_inventory import known_executor_kinds, supported_executor_kinds


def test_first_party_executors_are_registered() -> None:
    known = set(known_executor_kinds())
    assert {"acp", "openai-http"} <= known
    assert set(supported_executor_kinds()) == known
    assert "not-a-real-executor" not in known


def test_probe_commands_returns_the_first_hit() -> None:
    name, path = probe_commands(
        ("python3", "python"),
        which=lambda n: "/bin/x" if n == "python3" else None,
    )
    assert (name, path) == ("python3", "/bin/x")
