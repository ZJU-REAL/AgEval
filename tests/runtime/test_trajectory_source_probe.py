"""Phase 0 probe: Codex event source is collectable (not stdout-only prose)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bora.adapters.agent_codex import CodexExecutor, _parse_codex_jsonl
from bora.evidence.store import AttemptEvidenceStore, parse_jsonl_recover


def test_parse_codex_jsonl_events() -> None:
    sample = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "item.completed", "item": {"text": '{"answer": 1}'}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3}}),
        ]
    )
    events, structured, text, usage = _parse_codex_jsonl(sample)
    assert len(events) == 3
    assert events[0]["source"] == "codex"
    assert structured is not None or "answer" in text
    assert usage is not None


def test_offline_still_emits_lifecycle_events() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        r = CodexExecutor(model="gpt-5.4-mini").invoke("hi")
        assert r.ok is False
        assert r.error == "offline_forced"
        assert any(e.get("type") == "lifecycle" for e in r.events)
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


@pytest.mark.skipif(
    os.environ.get("BORA_SKIP_REAL_CODEX") == "1",
    reason="explicit skip real codex probe",
)
def test_real_codex_json_events_when_available(tmp_path: Path) -> None:
    """If codex binary + network available, collect JSONL events with digests."""
    import shutil

    if shutil.which("codex") is None:
        pytest.skip("codex not on PATH")
    if os.environ.get("BORA_OFFLINE_AGENT") == "1":
        pytest.skip("offline forced")

    store = AttemptEvidenceStore(root=tmp_path / "ev", attempt_id="probe")
    h = store.begin_invocation(profile_id="p", executor_kind="codex", model="gpt-5.4-mini")
    h.write_request(
        {"messages": [{"role": "user", "content": 'Reply with JSON {"ok":true} only.'}]}
    )
    ex = CodexExecutor(model="gpt-5.4-mini")
    result = ex.invoke(
        'Reply with ONLY JSON {"ok": true} and nothing else.',
        timeout=120.0,
        collect_dir=h.directory / "backend_raw",
    )
    for ev in result.events:
        h.append_event(ev)
    if result.stderr:
        h.write_stderr(result.stderr)
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
    # Must have adapter lifecycle and/or backend events — not empty.
    assert len(events) >= 1
    # Source refs prove collection beyond pure prose when raw persisted.
    if result.source_refs:
        assert any(r.get("digest", "").startswith("sha256:") for r in result.source_refs)
    meta = json.loads((h.directory / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] in {"completed", "failed", "timeout"}
