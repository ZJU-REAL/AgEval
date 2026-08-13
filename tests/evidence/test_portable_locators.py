"""Portable evidence locators (#70) — no host absolute paths in sealed products."""

from __future__ import annotations

import json
from pathlib import Path

from bora.evidence.locators import (
    portable_artifact_ref,
    portable_run_locator,
    resolve_run_dir,
    seal_harness_for_evidence,
)
from bora.evidence.store import AttemptEvidenceStore


def test_portable_run_locator_relative_to_database(tmp_path: Path) -> None:
    db = tmp_path / "my-db"
    run = db / ".bora" / "runs" / "sha256_deadbeef_run_abc123"
    run.mkdir(parents=True)
    assert portable_run_locator(run, database_root=db) == ".bora/runs/sha256_deadbeef_run_abc123"
    # Without database_root, still strip to .bora/runs/<id>
    assert portable_run_locator(run) == ".bora/runs/sha256_deadbeef_run_abc123"


def test_portable_run_locator_never_seals_home_style(tmp_path: Path) -> None:
    # Simulate a host abs path that still has the standard suffix
    fake = Path("/Users/someone/proj/.bora/runs/sha256_x_run_y")
    loc = portable_run_locator(fake)
    assert loc == ".bora/runs/sha256_x_run_y"
    assert "/Users/" not in loc
    assert not loc.startswith("/")


def test_store_locator_and_summary_portable(tmp_path: Path) -> None:
    db = tmp_path / "db"
    run_id = "sha256_packagedigest_run_attempt1"
    run = db / ".bora" / "runs" / run_id
    store = AttemptEvidenceStore(
        root=run,
        attempt_id="attempt_1",
        run_id="run_1",
        database_root=db,
    )
    assert store.locator == f".bora/runs/{run_id}"
    store.write_summary({"status": "PASS", "score": 1.0, "logs": store.locator})
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["evidence_root"] == f".bora/runs/{run_id}"
    blob = json.dumps(summary)
    assert "/Users/" not in blob
    assert "/var/folders/" not in blob
    assert str(tmp_path) not in summary["evidence_root"]


def test_seal_harness_strips_hold_abs(tmp_path: Path) -> None:
    hold = tmp_path / "bora-artifacts-xyz"
    hold.mkdir()
    art = hold / "session-output.json"
    art.write_text("{}", encoding="utf-8")
    harness_out = {
        "attempt": "a1",
        "artifact_hold": str(hold),
        "envelope": {
            "ok": True,
            "published": {"session-output": str(art)},
        },
    }
    sealed = seal_harness_for_evidence(harness_out, run_dir=tmp_path / "run")
    assert sealed["artifact_hold"] is True
    assert sealed["envelope"]["published"]["session-output"] == "session-output.json"
    assert "/var/folders" not in json.dumps(sealed)
    assert str(tmp_path) not in sealed["envelope"]["published"]["session-output"]
    # Original in-memory paths unchanged for evaluation
    assert harness_out["artifact_hold"] == str(hold)


def test_portable_artifact_ref_basename_fallback(tmp_path: Path) -> None:
    p = Path("/var/folders/xx/bora-artifacts-1/session-output.json")
    assert portable_artifact_ref(p) == "session-output.json"


def test_resolve_run_dir_portable_and_legacy(tmp_path: Path) -> None:
    db = tmp_path / "db"
    rid = "sha256_abc_run_def"
    run = db / ".bora" / "runs" / rid
    run.mkdir(parents=True)
    (run / "result.json").write_text("{}", encoding="utf-8")

    assert resolve_run_dir(db, f".bora/runs/{rid}") == run.resolve()
    assert resolve_run_dir(db, rid) == run.resolve()
    # legacy absolute
    assert resolve_run_dir(db, str(run)) == run.resolve()


def test_write_l1_evidence_portable(tmp_path: Path) -> None:
    from bora.application.run_l1_evidence import write_l1_evidence

    db = tmp_path / "db"
    rid = "sha256_l1_run_zzz"
    run = db / ".bora" / "runs" / rid
    doc: dict = {"status": "ERROR", "score": None}
    write_l1_evidence(
        run,
        doc,
        {"executor_containment": "attempt-container"},
        {"probe": True},
        database_root=db,
    )
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    l1 = json.loads((run / "l1.json").read_text(encoding="utf-8"))
    for blob in (result, summary, l1):
        text = json.dumps(blob)
        assert "/Users/" not in text
        assert "/var/folders/" not in text
        # Sealed locators must not embed the host Database absolute path
        assert str(db.resolve()) not in text
    assert result["logs"] == f".bora/runs/{rid}"
    assert result["evidence_path"] == f".bora/runs/{rid}"
    assert result["l1"]["evidence_volume"] == f".bora/runs/{rid}"
    assert summary["evidence_root"] == f".bora/runs/{rid}"
    assert l1["evidence_volume"] == f".bora/runs/{rid}"


def test_export_source_evidence_portable(tmp_path: Path) -> None:
    from bora.evidence.export import export_trajectory

    db = tmp_path / "db"
    rid = "sha256_exp_run_1"
    run = db / ".bora" / "runs" / rid
    store = AttemptEvidenceStore(root=run, attempt_id="a", database_root=db)
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
    assert man["source_evidence"] == f".bora/runs/{rid}"
    assert "/Users/" not in man["source_evidence"]


def test_l1_error_seals_harness_published_without_abs(tmp_path: Path) -> None:
    """L1 error path must not dump hold abs paths into sealed l1.harness (#70 review)."""
    from bora.application.run_l1_evidence import l1_error_result

    db = tmp_path / "db"
    rid = "sha256_err_run_1"
    run = db / ".bora" / "runs" / rid
    hold = tmp_path / "bora-artifacts-secret"
    hold.mkdir()
    art = hold / "session-output.json"
    art.write_text("{}", encoding="utf-8")
    envelope = {
        "ok": False,
        "published": {"session-output": str(art)},
        "terminal": {"kind": "failed"},
    }
    code, doc, details = l1_error_result(
        run,
        "evaluation_input",
        {
            "harness": envelope,
        },
        {"executor_containment": "attempt-container"},
        0,
        kind="missing_artifact",
    )
    assert code == 2
    text = json.dumps({"doc": doc, "details": details})
    assert "/var/folders/" not in text
    assert str(hold) not in text
    assert str(tmp_path.resolve()) not in json.dumps(doc.get("l1") or {})
    sealed = (doc.get("l1") or {}).get("harness") or {}
    pub = sealed.get("published") or {}
    assert pub.get("session-output") == "session-output.json"
    on_disk = json.loads((run / "l1.json").read_text(encoding="utf-8"))
    assert str(hold) not in json.dumps(on_disk)
    assert (on_disk.get("harness") or {}).get("published", {}).get(
        "session-output"
    ) == "session-output.json"
