"""ACP static registry loader and readiness (Spec 19 Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bora.plugins.contrib.acp.registry import (
    clear_registry_cache,
    get_entry,
    list_entry_ids,
    load_acp_entries,
    readiness_for,
)


def test_registry_loads_five_entries() -> None:
    clear_registry_cache()
    entries = load_acp_entries()
    assert set(entries) == {"codex", "claude-code", "pi", "opencode", "grok-build"}
    for eid in list_entry_ids():
        desc = entries[eid]
        assert desc.execution_mode == "acp-stdio"
        assert desc.descriptor_digest.startswith("sha256:")
        assert desc.acp_command
        assert "latest" not in " ".join(desc.acp_command)


def test_unknown_entry() -> None:
    assert get_entry("not-a-real-entry") is None


def test_duplicate_entry_rejected(tmp_path: Path) -> None:
    clear_registry_cache()
    src = Path(__file__).resolve().parents[2] / "src/bora/plugins/contrib/acp/acp_entries.json"
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["entries"].append(doc["entries"][0])
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_acp_entries(str(bad))
    clear_registry_cache()


def test_adapter_missing_readiness() -> None:
    desc = get_entry("codex")
    assert desc is not None

    def which(name: str) -> str | None:
        if name == "codex":
            return "/fake/codex"
        return None

    row = readiness_for(desc, which=which)
    assert row["engine_ready"] is True
    assert row["acp_entry_ready"] is False
    assert row["readiness"] == "adapter-missing"


def test_mode2_entry_missing() -> None:
    desc = get_entry("opencode")
    assert desc is not None

    def which(_name: str) -> str | None:
        return None

    row = readiness_for(desc, which=which)
    assert row["readiness"] == "entry-missing"


def test_lock_snapshot_has_no_paths_or_secrets() -> None:
    desc = get_entry("pi")
    assert desc is not None
    snap = desc.as_lock_snapshot()
    blob = json.dumps(snap)
    assert "secret" not in blob.lower() or "credential_env" in blob
    assert "/Users" not in blob
    assert "/home" not in blob
    assert "sk-" not in blob
    assert snap["entry_id"] == "pi"
    assert snap["acp_version"] == "0.0.33"
