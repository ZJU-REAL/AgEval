"""ACP entry feasibility: offline paths + PATH readiness (no secret output)."""

from __future__ import annotations

import os
import shutil

import pytest

from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES
from bora.plugins.contrib.acp import AcpExecutor
from bora.plugins.contrib.acp.registry import get_entry, list_entry_ids, readiness_for


def test_acp_offline_forced() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        r = AcpExecutor(entry_id="opencode", model="entry-default").invoke("hi")
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
    for eid in list_entry_ids():
        desc = get_entry(eid)
        assert desc is not None
        for name in desc.credential_env_names:
            assert not name.startswith("sk-")


@pytest.mark.skipif(shutil.which("pi") is None, reason="pi not on PATH")
def test_pi_engine_present() -> None:
    assert shutil.which("pi")


@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode not on PATH")
def test_opencode_entry_present() -> None:
    assert shutil.which("opencode")


def test_five_acp_entries_registered() -> None:
    ids = set(list_entry_ids())
    assert {"codex", "claude-code", "pi", "opencode", "grok-build"} <= ids
    for eid in ids:
        row = readiness_for(get_entry(eid))  # type: ignore[arg-type]
        assert row["readiness"] in {
            "ready",
            "engine-missing",
            "adapter-missing",
            "entry-missing",
            "unsupported-platform",
        }
