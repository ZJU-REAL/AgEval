"""ACP credential_missing on --probe (fail-closed vs keyless warning)."""

from __future__ import annotations

from ageval.adapters.executor_inventory import describe_acp_entry
from ageval.application.attempt.probe_command import _probe_first_party


def _cred_check(entry: str, environ: dict[str, str], *, api_key: str | None = None) -> dict:
    binding: dict[str, object] = {"role": "main", "executor": "acp", "entry": entry}
    if api_key:
        binding["api_key"] = api_key
    checks = _probe_first_party(
        binding=binding,
        path="l0",
        environ=environ,
        which=lambda name: f"/bin/{name}",
    )
    rows = [c for c in checks if c["id"] == "credential_missing"]
    assert rows, checks
    return rows[0]


def test_probe_fail_closed_for_required_entry() -> None:
    row = _cred_check("pi", {})
    assert row["missing"] is True
    assert row["ok"] is False
    assert row["status"] == "credential_missing"
    assert row["policy"] == "required"


def test_probe_warning_only_for_keyless_entry() -> None:
    row = _cred_check("codex", {})
    assert row["missing"] is False
    assert row["ok"] is True
    assert row["policy"] == "optional"


def test_probe_warning_when_keyless_names_unset() -> None:
    row = _cred_check("claude-code", {})
    assert row["missing"] is True
    assert row["ok"] is True
    assert row["status"] == "credential_missing"
    assert row["policy"] == "optional"


def test_probe_present_locator_clears_missing() -> None:
    row = _cred_check("pi", {"MY_KEY": "x"}, api_key="MY_KEY")
    assert row["missing"] is False
    assert row["ok"] is True


def test_inventory_verbose_reports_credential_missing() -> None:
    missing = describe_acp_entry("pi", verbose=True, environ={})
    assert missing["credential_missing"] is True
    present = describe_acp_entry("pi", verbose=True, environ={"ZAI_API_KEY": "k"})
    assert present["credential_missing"] is False
    codex = describe_acp_entry("codex", verbose=True, environ={})
    assert codex["credential_missing"] is False
    assert codex["keyless_auth"] is True
