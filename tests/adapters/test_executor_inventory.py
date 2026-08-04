"""Unit tests for executor inventory (no full CLI process)."""

from __future__ import annotations

from bora.adapters.executor_inventory import (
    build_executor_inventory,
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


def test_describe_cli_missing_binary() -> None:
    row = describe_executor("pi", which=lambda _n: None, verbose=False)
    assert row["kind"] == "pi"
    assert row["execution_mode"] == "cli-process"
    assert row["binary_on_path"] is False
    assert row["host_ready"] is False
    assert "credential_env_names" not in row


def test_describe_api_client_no_binary() -> None:
    row = describe_executor("openai-http", which=lambda _n: None, verbose=False)
    assert row["execution_mode"] == "api-client"
    assert row["binary_on_path"] is None
    assert row["host_ready"] is True


def test_verbose_includes_credential_env_names() -> None:
    row = describe_executor("claude-code", which=lambda _n: None, verbose=True)
    assert "ANTHROPIC_AUTH_TOKEN" in row["credential_env_names"]


def test_inventory_aggregates() -> None:
    def fake_which(name: str) -> str | None:
        return {"codex": "/bin/codex"}.get(name)

    inv = build_executor_inventory(which=fake_which, verbose=False)
    assert "codex" in inv["supported"]
    assert "pi" in inv["supported"]
    assert "codex" in inv["host_ready"]
    assert "pi" in inv["missing_binary"]
    assert "required_v014" not in inv
