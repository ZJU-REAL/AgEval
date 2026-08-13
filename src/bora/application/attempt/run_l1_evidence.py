"""L1 Attempt evidence writers and early-error result binding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora.evidence.locators import portable_run_locator, seal_harness_for_evidence


def _infer_database_root(run_dir: Path) -> Path | None:
    from bora.evidence.attempt_record import infer_database_root_from_run_dir

    return infer_database_root_from_run_dir(run_dir)


def _seal_l1_meta_for_evidence(
    l1_meta: dict[str, Any],
    *,
    run_dir: Path,
) -> dict[str, Any]:
    """Strip host abs paths from nested harness envelopes before seal (#70)."""
    out = dict(l1_meta)
    harness = out.get("harness")
    if isinstance(harness, dict):
        # envelope-only or full harness_out shape
        if "envelope" in harness or "artifact_hold" in harness:
            sealed = seal_harness_for_evidence(harness, run_dir=run_dir)
            out["harness"] = sealed.get("envelope") if "envelope" in harness else sealed
        elif "published" in harness:
            sealed = seal_harness_for_evidence(
                {"envelope": harness, "artifact_hold": harness.get("artifact_hold")},
                run_dir=run_dir,
            )
            out["harness"] = sealed.get("envelope") or harness
    return out


def l1_error_result(
    run_dir: Path,
    phase: str,
    l1_meta: dict[str, Any],
    agent_meta: dict[str, Any],
    inv: int,
    *,
    kind: str | None = None,
    phase_timing: dict[str, Any] | None = None,
    database_root: Path | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    from bora.evaluation.result_binding import bind_result

    db_root = database_root if database_root is not None else _infer_database_root(run_dir)
    locator = portable_run_locator(run_dir, database_root=db_root)
    flat = bind_result(
        evaluator_raw=None,
        harness_kind="failed",
        runtime_kind="docker_l1",
        agent_invocations=inv,
        evidence_path=locator,
        error_phase=phase,
        logs=locator,
    )
    doc = flat.as_dict()
    doc["assurance"] = "l0"
    doc["status"] = "ERROR"
    if kind:
        doc["error"] = {"phase": phase, "kind": kind}
    sealed_meta = _seal_l1_meta_for_evidence(l1_meta, run_dir=run_dir)
    doc["l1"] = sealed_meta
    if isinstance(phase_timing, dict):
        doc["phase_timing"] = phase_timing
        total_ms = phase_timing.get("total_ms")
        if isinstance(total_ms, int | float) and not isinstance(total_ms, bool):
            from bora.application.attempt.phase_timing import format_duration_ms

            doc["duration"] = format_duration_ms(float(total_ms))
    write_l1_evidence(run_dir, doc, agent_meta, sealed_meta, database_root=db_root)
    details: dict[str, Any] = {
        "agent": agent_meta,
        "l1": sealed_meta,
        "assurance": "l0",
        "logs": locator,
    }
    if isinstance(phase_timing, dict):
        details["phase_timing"] = phase_timing
    return 2, doc, details


def write_l1_evidence(
    run_dir: Path,
    result_doc: dict[str, Any],
    agent_meta: dict[str, Any],
    l1_meta: dict[str, Any],
    *,
    database_root: Path | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    db_root = database_root if database_root is not None else _infer_database_root(run_dir)
    locator = portable_run_locator(run_dir, database_root=db_root)
    # Result.logs / evidence_path (design §8.9) — portable under Database root.
    # Mutate in place so caller-returned doc/details stay aligned with disk.
    result_doc["logs"] = locator
    result_doc["evidence_path"] = locator
    # Honest execution location facts (Spec 14 / v0.15).
    containment = str(
        agent_meta.get("executor_containment") or l1_meta.get("executor_containment") or "unknown"
    )
    if containment in {"container", "attempt-container"}:
        exec_loc = "attempt-container"
    elif containment.startswith("parent"):
        exec_loc = "parent-api-client"
    else:
        # Harness/eval containers still run under Docker even when Agent is parent.
        exec_loc = str(l1_meta.get("execution_location") or "mixed")
    l1_meta = _seal_l1_meta_for_evidence(
        {
            **l1_meta,
            "execution_location": exec_loc,
            "executor_containment": containment,
            "evidence_volume": locator,
        },
        run_dir=run_dir,
    )
    from bora.evidence.attempt_record import (
        AGENT_FILENAME,
        L1_FILENAME,
        write_attempt_json,
        write_attempt_result,
    )
    from bora.evidence.redaction import RedactionError, redact_and_assert, redact_value

    result_doc["l1"] = {**(result_doc.get("l1") or {}), **l1_meta}
    write_attempt_result(run_dir, result_doc)
    write_attempt_json(run_dir, AGENT_FILENAME, agent_meta)
    # Fail-closed redaction (no string-replace self-confirm).
    try:
        safe = redact_and_assert(l1_meta)
    except RedactionError:
        safe = redact_value(l1_meta)
    write_attempt_json(run_dir, L1_FILENAME, safe if isinstance(safe, dict) else {"redacted": True})
    # §8.9 summary + skeletons (trajectory body still owned by Agent Service when used).
    summary = {
        "schema": "bora.evidence.summary/1",
        "status": result_doc.get("status"),
        "score": result_doc.get("score"),
        "assurance": result_doc.get("assurance"),
        "evidence_root": locator,
        "logs": result_doc.get("logs"),
        "execution_location": exec_loc,
        "l1": safe,
    }
    if isinstance(result_doc.get("phase_timing"), dict):
        summary["phase_timing"] = result_doc["phase_timing"]
        pt = result_doc["phase_timing"]
        if pt.get("started_at"):
            summary["started_at"] = pt.get("started_at")
        if pt.get("finished_at"):
            summary["finished_at"] = pt.get("finished_at")
    if result_doc.get("duration") is not None:
        summary["duration"] = result_doc.get("duration")
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for rel in ("effects.jsonl", "agent/events.jsonl"):
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    (run_dir / "cleanup.json").write_text(
        json.dumps({"ok": True, "warning": result_doc.get("cleanup_warning")}, indent=2) + "\n",
        encoding="utf-8",
    )
