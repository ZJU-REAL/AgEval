"""Trajectory export re-redacts, digests, and refuses unsealed evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ageval.evidence.export import export_trajectory
from ageval.evidence.store import AttemptEvidenceStore


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
    src_req = (store.list_invocations()[0] / "request.json").read_text(encoding="utf-8")
    assert "EXPORT_SECRET_XYZ" not in src_req
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert man["schema"] == "ageval.trajectory.export/1"
    assert man["invocation_count"] == 1
    inv = man["invocations"][0]
    assert inv["sealed"] is True
    assert inv["source_digests"]
    assert all(v.startswith("sha256:") for v in inv["source_digests"].values())
    exp_req = (dest / "invocations" / store.list_invocations()[0].name / "request.json").read_text(
        encoding="utf-8"
    )
    assert "EXPORT_SECRET_XYZ" not in exp_req


def test_export_refuses_unsealed(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "src", attempt_id="a")
    store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
    # left running — unsealed
    r = export_trajectory(store.root, tmp_path / "out")
    assert r.ok is False
    assert r.error and r.error.startswith("unsealed_invocation:")


def test_export_missing_root(tmp_path: Path) -> None:
    r = export_trajectory(tmp_path / "nope", tmp_path / "out")
    assert r.ok is False
    assert r.error == "evidence_root_missing"


def test_export_succeeds_on_slim_tree_without_invocation_meta(tmp_path: Path) -> None:
    from ageval.evidence.slim import slim_sealed_attempt

    store = AttemptEvidenceStore(root=tmp_path / "src", attempt_id="a")
    h = store.begin_invocation(profile_id="p", executor_kind="openai-http", model="m")
    h.write_request({"messages": [{"role": "user", "content": "hi"}]})
    h.append_event({"type": "message", "text": "ok"})
    h.seal(
        status="completed",
        final_response={"content": "done", "structured_output": None, "usage": None},
        latency_ms=4.0,
    )
    (store.root / "trajectory.jsonl").write_text(
        json.dumps({"type": "terminal", "ok": True, "elapsed_ms": 4.0}) + "\n",
        encoding="utf-8",
    )
    slim_sealed_attempt(store.root)
    dest = tmp_path / "export-slim"
    result = export_trajectory(store.root, dest)
    assert result.ok, result.error
    assert (dest / "trajectory.jsonl").is_file()


def test_export_copies_layer_c_trajectory(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "src", attempt_id="a")
    h = store.begin_invocation(profile_id="p", executor_kind="openai-http", model="m")
    h.write_request({"messages": [{"role": "user", "content": "hi"}]})
    h.append_event({"type": "message", "text": "ok"})
    h.seal(
        status="completed",
        final_response={
            "content": "done",
            "structured_output": None,
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        },
        latency_ms=12.0,
    )
    (store.root / "trajectory.jsonl").write_text(
        json.dumps(
            {
                "type": "terminal",
                "ok": True,
                "elapsed_ms": 12.0,
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                "metadata": {"profile_id": "p", "latency_ms": 12.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / "export"
    result = export_trajectory(store.root, dest)
    assert result.ok
    copied = dest / "trajectory.jsonl"
    assert copied.is_file()
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert man["trajectory"] == "trajectory.jsonl"
    row = json.loads(copied.read_text(encoding="utf-8").splitlines()[0])
    assert row["usage"]["prompt_tokens"] == 3
    assert row["elapsed_ms"] == 12.0
