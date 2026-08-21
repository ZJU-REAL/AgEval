"""Portable evidence locators (#70) — no host absolute paths in sealed products."""

from __future__ import annotations

import json
from pathlib import Path

from ageval.evidence.locators import (
    portable_artifact_ref,
    portable_run_locator,
    resolve_run_dir,
)
from ageval.evidence.store import AttemptEvidenceStore


def test_portable_run_locator_relative_to_dataset(tmp_path: Path) -> None:
    db = tmp_path / "my-db"
    run = db / ".ageval" / "runs" / "sha256_deadbeef_run_abc123"
    run.mkdir(parents=True)
    assert portable_run_locator(run, dataset_root=db) == ".ageval/runs/sha256_deadbeef_run_abc123"
    # Without dataset_root, still strip to .ageval/runs/<id>
    assert portable_run_locator(run) == ".ageval/runs/sha256_deadbeef_run_abc123"


def test_portable_run_locator_never_seals_home_style(tmp_path: Path) -> None:
    # Simulate a host abs path that still has the standard suffix
    fake = Path("/Users/someone/proj/.ageval/runs/sha256_x_run_y")
    loc = portable_run_locator(fake)
    assert loc == ".ageval/runs/sha256_x_run_y"
    assert "/Users/" not in loc
    assert not loc.startswith("/")


def test_store_locator_and_summary_portable(tmp_path: Path) -> None:
    db = tmp_path / "db"
    run_id = "sha256_packagedigest_run_attempt1"
    run = db / ".ageval" / "runs" / run_id
    store = AttemptEvidenceStore(
        root=run,
        attempt_id="attempt_1",
        run_id="run_1",
        dataset_root=db,
    )
    assert store.locator == f".ageval/runs/{run_id}"
    store.write_summary({"status": "PASS", "score": 1.0, "logs": store.locator})
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["evidence_root"] == f".ageval/runs/{run_id}"
    blob = json.dumps(summary)
    assert "/Users/" not in blob
    assert "/var/folders/" not in blob
    assert str(tmp_path) not in summary["evidence_root"]


def test_portable_artifact_ref_basename_fallback(tmp_path: Path) -> None:
    p = Path("/var/folders/xx/ageval-artifacts-1/session-output.json")
    assert portable_artifact_ref(p) == "session-output.json"


def test_resolve_run_dir_portable_and_legacy(tmp_path: Path) -> None:
    db = tmp_path / "db"
    rid = "sha256_abc_run_def"
    run = db / ".ageval" / "runs" / rid
    run.mkdir(parents=True)
    (run / "result.json").write_text("{}", encoding="utf-8")

    assert resolve_run_dir(db, f".ageval/runs/{rid}") == run.resolve()
    assert resolve_run_dir(db, rid) == run.resolve()
    # legacy absolute
    assert resolve_run_dir(db, str(run)) == run.resolve()


def test_export_source_evidence_portable(tmp_path: Path) -> None:
    from ageval.evidence.export import export_trajectory

    db = tmp_path / "db"
    rid = "sha256_exp_run_1"
    run = db / ".ageval" / "runs" / rid
    store = AttemptEvidenceStore(root=run, attempt_id="a", dataset_root=db)
    h = store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
    h.write_request({"messages": [{"role": "user", "content": "hi"}]})
    h.seal(
        status="completed",
        final_response={"content": "ok", "structured_output": None, "usage": None},
        latency_ms=1.0,
    )
    dest = tmp_path / "export"
    result = export_trajectory(store.root, dest)
    assert result.ok
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert man["source_evidence"] == f".ageval/runs/{rid}"
    assert "/Users/" not in man["source_evidence"]
