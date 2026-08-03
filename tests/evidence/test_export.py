"""Trajectory export re-redacts and does not mutate source."""

from __future__ import annotations

import json
from pathlib import Path

from bora.evidence.export import export_trajectory
from bora.evidence.store import AttemptEvidenceStore


def test_export_redacts_and_preserves_source(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(
        root=tmp_path / "src",
        attempt_id="a",
        sentinels=["EXPORT_SECRET_XYZ"],
    )
    h = store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
    h.write_request({"messages": [{"role": "user", "content": "hi EXPORT_SECRET_XYZ"}]})
    h.append_event({"type": "message", "text": "ok"})
    h.seal(
        status="completed",
        final_response={"content": "done", "structured_output": {"answer": 1}, "usage": None},
        latency_ms=1.0,
    )
    dest = tmp_path / "export"
    result = export_trajectory(store.root, dest, extra_sentinels=["EXPORT_SECRET_XYZ"])
    assert result.ok
    assert result.invocation_count == 1
    # Source request still sealed under store redaction policy
    src_req = (store.list_invocations()[0] / "request.json").read_text(encoding="utf-8")
    assert "EXPORT_SECRET_XYZ" not in src_req
    # Export has manifest
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert man["schema"] == "bora.trajectory.export/1"
    assert man["invocation_count"] == 1
    exp_req = (dest / "invocations" / store.list_invocations()[0].name / "request.json").read_text(
        encoding="utf-8"
    )
    assert "EXPORT_SECRET_XYZ" not in exp_req


def test_export_missing_root(tmp_path: Path) -> None:
    r = export_trajectory(tmp_path / "nope", tmp_path / "out")
    assert r.ok is False
    assert r.error == "evidence_root_missing"
