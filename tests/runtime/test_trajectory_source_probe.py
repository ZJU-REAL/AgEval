"""ACP trajectory source probe — offline lifecycle + validated-text policy."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bora.adapters.agent_acp import AcpExecutor
from bora.adapters.agent_contract import parse_validated_text_structured
from bora.evidence.store import AttemptEvidenceStore, parse_jsonl_recover


def test_validated_text_no_regex_salvage() -> None:
    assert parse_validated_text_structured('{"answer": 1}') == {"answer": 1}
    assert parse_validated_text_structured('prefix {"answer": 1}') is None


def test_acp_offline_still_emits_lifecycle_events() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        r = AcpExecutor(entry_id="opencode", model="entry-default").invoke("hi")
        assert r.ok is False
        assert r.error == "offline_forced"
        assert any(e.get("type") == "lifecycle" for e in r.events)
        assert r.metadata is not None
        assert r.metadata.get("executor_kind") == "acp"
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


@pytest.mark.skipif(
    os.environ.get("BORA_SKIP_REAL_ACP") == "1",
    reason="explicit skip real ACP probe",
)
def test_real_acp_opencode_events_when_available(tmp_path: Path) -> None:
    import shutil

    if shutil.which("opencode") is None:
        pytest.skip("opencode not on PATH")
    if os.environ.get("BORA_OFFLINE_AGENT") == "1":
        pytest.skip("offline forced")

    store = AttemptEvidenceStore(root=tmp_path / "ev", attempt_id="probe")
    h = store.begin_invocation(profile_id="p", executor_kind="acp", model="entry-default")
    h.write_request(
        {
            "messages": [{"role": "user", "content": 'Reply with JSON {"ok":true} only.'}],
            "acp_entry_id": "opencode",
        }
    )
    ex = AcpExecutor(entry_id="opencode", model="entry-default")
    try:
        result = ex.invoke(
            'Reply with ONLY JSON {"ok": true} and nothing else.',
            timeout=120.0,
            collect_dir=h.directory / "backend_raw",
        )
    finally:
        ex.close()
    for ev in result.events:
        h.append_event(ev)
    status = "completed" if result.ok else "failed"
    h.seal(
        status=status,
        final_response=(
            {
                "content": result.text,
                "structured_output": result.structured,
                "usage": result.usage,
            }
            if result.ok
            else None
        ),
        error=result.error,
        latency_ms=1.0,
    )
    events = parse_jsonl_recover(h.directory / "events.jsonl")
    assert len(events) >= 1
    meta = json.loads((h.directory / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] in {"completed", "failed", "timeout"}
