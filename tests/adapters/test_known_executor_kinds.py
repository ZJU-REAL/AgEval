"""Single source for known executor kind declarations."""

from __future__ import annotations

from bora.adapters.executor_inventory import known_executor_kinds, supported_executor_kinds
from bora.adapters.path_probe import probe_commands
from bora.config.capabilities import DeclarationCapabilityCatalog


def test_catalog_matches_known_executor_kinds() -> None:
    catalog = DeclarationCapabilityCatalog()
    known = known_executor_kinds()
    assert set(supported_executor_kinds()) == set(known)
    for kind in ("Official/acp", "Official/mock", "Official/openai-http"):
        assert catalog.supports_executor_kind(kind)
        assert kind in known
    assert not catalog.supports_executor_kind("not-a-real-executor")


def test_probe_commands_shared() -> None:
    name, path = probe_commands(
        ("python3", "python"), which=lambda n: "/bin/x" if n == "python3" else None
    )
    assert name == "python3"
    assert path == "/bin/x"
