"""Phase 0 feasibility: offline paths + binary presence (no secret output)."""

from __future__ import annotations

import os
import shutil

import pytest

from bora.adapters.agent_opencode import OpenCodeExecutor
from bora.adapters.agent_pi import PiExecutor
from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES


def test_pi_offline_forced() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        r = PiExecutor(model="claude-haiku-4-5").invoke("hi")
        assert r.ok is False
        assert r.error == "offline_forced"
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


def test_opencode_offline_forced() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        r = OpenCodeExecutor().invoke("hi")
        assert r.ok is False
        assert r.error == "offline_forced"
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


def test_capability_credential_names_are_locators_only() -> None:
    for _kind, cap in BUILTIN_CAPABILITIES.items():
        for name in cap.credential_env_names:
            assert name.isupper() or "_" in name
            assert not name.startswith("sk-")
            assert "=" not in name


@pytest.mark.skipif(shutil.which("pi") is None, reason="pi not on PATH")
def test_pi_binary_present() -> None:
    assert shutil.which("pi")


@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode not on PATH")
def test_opencode_binary_present() -> None:
    assert shutil.which("opencode")


def test_claude_code_residual_when_missing() -> None:
    from bora.adapters.agent_registry import discover_executor_kinds

    kinds = discover_executor_kinds()
    # Required three always registered; claude-code is residual when binary missing.
    assert {"codex", "pi", "opencode"}.issubset(kinds)
