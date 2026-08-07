"""L1 Attempt evidence writers and early-error result binding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def l1_error_result(
    run_dir: Path,
    phase: str,
    l1_meta: dict[str, Any],
    agent_meta: dict[str, Any],
    inv: int,
    *,
    kind: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    from bora.evaluation.result_binding import bind_result

    flat = bind_result(
        evaluator_raw=None,
        harness_kind="failed",
        runtime_kind="docker_l1",
        agent_invocations=inv,
        evidence_path=str(run_dir),
        error_phase=phase,
    )
    doc = flat.as_dict()
    doc["assurance"] = "l0"
    doc["status"] = "ERROR"
    if kind:
        doc["error"] = {"phase": phase, "kind": kind}
    doc["l1"] = l1_meta
    write_l1_evidence(run_dir, doc, agent_meta, l1_meta)
    return 2, doc, {"agent": agent_meta, "l1": l1_meta, "assurance": "l0"}


def write_l1_evidence(
    run_dir: Path,
    result_doc: dict[str, Any],
    agent_meta: dict[str, Any],
    l1_meta: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    # Result.logs locator (design §8.9) — evidence root on host, never secrets.
    # Mutate in place so caller-returned doc/details stay aligned with disk.
    result_doc.setdefault("logs", str(run_dir))
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
    l1_meta = {
        **l1_meta,
        "execution_location": exec_loc,
        "executor_containment": containment,
        "evidence_volume": str(run_dir),
    }
    result_doc["l1"] = {**(result_doc.get("l1") or {}), **l1_meta}
    (run_dir / "result.json").write_text(
        json.dumps(result_doc, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (run_dir / "agent.json").write_text(
        json.dumps(agent_meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    # Redact any accidental secret-looking keys from l1 dump.
    safe = json.loads(json.dumps(l1_meta, default=str))
    blob = json.dumps(safe, indent=2, sort_keys=True) + "\n"
    for needle in ("sk-", "OPENAI_API_KEY=", "password"):
        if needle in blob:
            blob = blob.replace(needle, "[REDACTED]")
    (run_dir / "l1.json").write_text(blob, encoding="utf-8")
    # §8.9 summary + skeletons (trajectory body still owned by Agent Service when used).
    summary = {
        "schema": "bora.evidence.summary/1",
        "status": result_doc.get("status"),
        "score": result_doc.get("score"),
        "assurance": result_doc.get("assurance"),
        "logs": result_doc.get("logs"),
        "execution_location": exec_loc,
        "l1": safe,
    }
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
