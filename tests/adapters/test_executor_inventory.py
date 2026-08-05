"""Unit tests for executor inventory (ACP + openai-http)."""

from __future__ import annotations

from bora.adapters.executor_inventory import (
    build_executor_inventory,
    describe_acp_entry,
    describe_executor,
    probe_binary,
)


def test_probe_binary_first_hit() -> None:
    def fake_which(name: str) -> str | None:
        return {"pi": "/usr/bin/pi"}.get(name)

    name, path = probe_binary(("pi", "pi-agent"), which=fake_which)
    assert name == "pi"
    assert path == "/usr/bin/pi"


def test_probe_binary_miss() -> None:
    name, path = probe_binary(("nope-cli",), which=lambda _n: None)
    assert name == "nope-cli"
    assert path is None


def test_describe_acp_kind() -> None:
    row = describe_executor("acp", which=lambda _n: None, verbose=False)
    assert row["kind"] == "acp"
    assert row["execution_mode"] == "acp-stdio"


def test_describe_api_client_no_binary() -> None:
    row = describe_executor("openai-http", which=lambda _n: None, verbose=False)
    assert row["execution_mode"] == "api-client"
    assert row["binary_on_path"] is None
    assert row["host_ready"] is True


def test_describe_acp_entry_adapter_missing() -> None:
    def which(name: str) -> str | None:
        if name == "codex":
            return "/fake/codex"
        return None

    row = describe_acp_entry("codex", which=which, verbose=True)
    assert row["readiness"] == "adapter-missing"
    assert row["engine_ready"] is True
    assert row["acp_entry_ready"] is False
    assert "install_command" in row


def test_inventory_aggregates() -> None:
    def fake_which(name: str) -> str | None:
        return {
            "codex": "/bin/codex",
            "codex-acp": "/bin/codex-acp",
            "opencode": "/bin/opencode",
        }.get(name)

    inv = build_executor_inventory(which=fake_which, verbose=False)
    assert "acp" in inv["supported"]
    assert "openai-http" in inv["supported"]
    assert "codex" not in inv["supported"]
    entry_ids = {r["entry_id"] for r in inv["acp_entries"]}
    assert "codex" in entry_ids
    assert "required_v014" not in inv
