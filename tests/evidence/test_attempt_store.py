"""Attempt evidence store: layout, seal, ordering, path safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bora.evidence.redaction import RedactionError
from bora.evidence.store import AttemptEvidenceStore, parse_jsonl_recover


def test_layout_contract(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="attempt_a", run_id="run_a")
    assert (store.root / "agent" / "invocations").is_dir()
    assert (store.root / "effects.jsonl").is_file()
    assert (store.root / "agent" / "events.jsonl").is_file()
    assert (store.root / "evaluation").is_dir()
    assert (store.root / "harness").is_dir()


def test_invocation_sequence_and_seal(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="attempt_b")
    h1 = store.begin_invocation(profile_id="p1", executor_kind="codex", model="m")
    h1.write_request({"messages": [{"role": "user", "content": "hi"}]})
    h1.append_event({"type": "lifecycle", "phase": "start"})
    h1.seal(
        status="completed",
        final_response={"content": "ok", "structured_output": {"a": 1}, "usage": None},
        latency_ms=12.5,
    )
    h2 = store.begin_invocation(profile_id="p1", executor_kind="codex", model="m")
    h2.write_request({"messages": [{"role": "user", "content": "again"}]})
    h2.seal(status="failed", error="exit_1", latency_ms=3.0)

    dirs = store.list_invocations()
    assert len(dirs) == 2
    assert dirs[0].name.startswith("0001-")
    assert dirs[1].name.startswith("0002-")
    meta1 = json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert meta1["status"] == "completed"
    assert meta1["attempt_id"] == "attempt_b"
    assert (dirs[0] / "final-response.json").is_file()
    assert not (dirs[1] / "final-response.json").exists()
    # Idempotent reseal
    h1.seal(status="failed", error="should_not_overwrite")
    meta1b = json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert meta1b["status"] == "completed"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="a")
    with pytest.raises(ValueError):
        store.path("../escape")
    with pytest.raises(ValueError):
        store.path("/etc/passwd")


def test_jsonl_recover_discards_incomplete_tail(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text('{"type":"a","seq":1}\n{"type":"b"', encoding="utf-8")
    rows = parse_jsonl_recover(p)
    assert len(rows) == 1
    assert rows[0]["type"] == "a"


def test_redaction_fail_closed_on_seal(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(
        root=tmp_path / "run",
        attempt_id="attempt_r",
        sentinels=["SUPER_SECRET_SENTINEL_XYZ"],
    )
    h = store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
    h.write_request({"messages": [{"role": "user", "content": "ok"}]})
    with pytest.raises(RedactionError):
        h.seal(
            status="completed",
            final_response={
                "content": "leaked SUPER_SECRET_SENTINEL_XYZ",
                "structured_output": None,
                "usage": None,
            },
            latency_ms=1.0,
        )
    meta = json.loads((h.directory / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] == "redaction_failed"
    tree = "\n".join(p.read_text(encoding="utf-8") for p in h.directory.rglob("*") if p.is_file())
    assert "SUPER_SECRET_SENTINEL_XYZ" not in tree


def test_effects_and_summary(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "run", attempt_id="a", run_id="r")
    store.append_effect({"decision": "allow", "capability": "tool", "name": "read"})
    store.write_summary({"status": "PASS", "score": 1.0})
    effects = parse_jsonl_recover(store.root / "effects.jsonl")
    assert effects[0]["decision"] == "allow"
    summary = json.loads((store.root / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert summary["evidence_root"] == store.locator
