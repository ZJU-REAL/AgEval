"""Invocation directory field contract."""

from __future__ import annotations

import json
from pathlib import Path

from ageval.evidence.store import AttemptEvidenceStore


def test_minimal_fields_present(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="attempt_x")
    h = store.begin_invocation(
        profile_id="codex-mini",
        executor_kind="codex",
        model="gpt-5.4-mini",
    )
    h.write_request(
        {
            "messages": [{"role": "user", "content": "Return JSON"}],
            "profile_id": "codex-mini",
            "executor_kind": "codex",
            "model": "gpt-5.4-mini",
        }
    )
    h.append_event({"type": "backend", "payload": {"msg": "partial"}})
    h.write_stderr("diag line\n")
    h.seal(
        status="completed",
        final_response={
            "content": '{"answer": 42}',
            "structured_output": {"answer": 42},
            "usage": {"input_tokens": 1},
            "session": {"reusable": False, "handle": None},
        },
        latency_ms=100.0,
    )
    d = h.directory
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    for key in (
        "invocation_id",
        "attempt_id",
        "profile_id",
        "executor_kind",
        "model",
        "started_at",
        "finished_at",
        "status",
        "latency_ms",
    ):
        assert key in meta
    req = json.loads((d / "request.json").read_text(encoding="utf-8"))
    assert req["messages"][0]["role"] == "user"
    events = (d / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(events) >= 1
    final = json.loads((d / "final-response.json").read_text(encoding="utf-8"))
    assert final["structured_output"]["answer"] == 42
    assert (d / "stderr.txt").read_text(encoding="utf-8").startswith("diag")


def test_partial_failure_no_final_response(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="attempt_y")
    for status in ("failed", "timeout", "cancelled", "crash"):
        h = store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
        h.write_request({"messages": [{"role": "user", "content": status}]})
        h.append_event({"type": "lifecycle", "phase": status})
        h.seal(status=status, error=status, latency_ms=1.0)
        assert not (h.directory / "final-response.json").exists()
        meta = json.loads((h.directory / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == status
