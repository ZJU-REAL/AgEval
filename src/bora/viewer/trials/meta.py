"""Trial list and detail APIs for the local viewer."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.viewer.browse import commands_for
from bora.viewer.jobs import get_job, get_job_task, safe_id_segment
from bora.viewer.trials.paths import (
    _read_json_object,
    _safe_run_id,
    resolve_evidence_root,
)
from bora.viewer.trials.surface import _trial_meta_from_evidence


def list_task_trials(
    database_root: Path,
    job_id: str,
    task_id: str,
) -> dict[str, Any]:
    """List trials for a task within a suite job, enriched with local evidence when present."""
    root = database_root.expanduser().resolve(strict=False)
    job_id = safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    task_payload = get_job_task(root, job_id, task_id)
    job = task_payload["job"]
    suite_trials = list(task_payload.get("trials") or [])

    by_run: dict[str, dict[str, Any]] = {}
    for tr in suite_trials:
        rid = tr.get("run_id") or tr.get("trial_id")
        if not rid:
            continue
        rid_s = str(rid)
        by_run[rid_s] = {
            "trial_id": rid_s,
            "run_id": rid_s,
            "task_id": task_id,
            "status": tr.get("status"),
            "score": tr.get("score") if tr.get("score") is not None else tr.get("reward"),
            "reward": tr.get("reward") if tr.get("reward") is not None else tr.get("score"),
            "error": tr.get("error"),
            "exit_code": tr.get("exit_code"),
            "duration": tr.get("duration"),
            "started": tr.get("started") or job.get("started"),
            "has_evidence": False,
            "available_tabs": [],
            "note": "from suite summary",
        }

    # Scan database-level and task-local runs matching this task_id via lock.json
    candidates: list[Path] = []
    from bora.evidence.locators import default_runs_root

    db_runs = default_runs_root(root)
    if db_runs.is_dir():
        candidates.extend(p for p in db_runs.iterdir() if p.is_dir())
    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    task_runs = default_runs_root(root / tasks_root_name / task_id)
    if task_runs.is_dir():
        candidates.extend(p for p in task_runs.iterdir() if p.is_dir())

    for run_dir in candidates:
        rid = run_dir.name
        lock = _read_json_object(run_dir / "lock.json") or {}
        locked_task = lock.get("task_id")
        # Enrich suite-listed runs always; only *add* new runs when lock matches task.
        if rid not in by_run and locked_task != task_id:
            continue
        suite_row = by_run.get(rid, {})
        meta = _trial_meta_from_evidence(
            run_dir,
            run_id=rid,
            task_id=task_id,
            suite_row=suite_row,
        )
        try:
            rel = str(run_dir.resolve(strict=False).relative_to(root))
        except ValueError:
            rel = str(run_dir)
        meta["evidence_relpath"] = rel
        meta["started"] = meta.get("started") or suite_row.get("started") or job.get("started")
        by_run[rid] = meta

    trials = sorted(
        by_run.values(),
        key=lambda t: (t.get("started") or "", t.get("run_id") or ""),
        reverse=True,
    )
    cmds = commands_for(root, task_id=task_id)
    return {
        "ok": True,
        "job": job,
        "task": task_payload["task"],
        "trials": trials,
        "count": len(trials),
        "commands": cmds,
        "run_command": cmds.get("run_task") or cmds.get("run_suite"),
        "breadcrumb": [
            {"label": "Jobs", "href": "/"},
            {"label": job_id, "href": f"/jobs/{job_id}"},
            {"label": task_id, "href": f"/jobs/{job_id}/tasks/{task_id}"},
            {"label": "trials", "href": None},
        ],
        "note": None,
    }


def get_trial(
    database_root: Path,
    job_id: str,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    job_id = safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    job_payload = get_job(root, job_id)
    job = job_payload["job"]
    suite_row: dict[str, Any] = {}
    for row in job_payload.get("tasks") or []:
        if row.get("task_id") == task_id and str(row.get("run_id") or "") == rid:
            suite_row = row
            break

    evidence: Path | None = None
    with contextlib.suppress(ConfigError):
        evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)

    result_preview: dict[str, Any] | None = None
    if evidence is None:
        if not suite_row:
            raise ConfigError(
                "unknown_task",
                f"trial {rid!r} not found for task {task_id!r} in job {job_id!r}",
                location=rid,
            )
        status = suite_row.get("status")
        meta = {
            "trial_id": rid,
            "run_id": rid,
            "task_id": task_id,
            "status": str(status).upper() if status else None,
            "score": suite_row.get("score"),
            "reward": suite_row.get("score"),
            "error": suite_row.get("error"),
            "exit_code": suite_row.get("exit_code"),
            "duration": suite_row.get("duration"),
            "started": suite_row.get("started") or job.get("started"),
            "evidence_relpath": None,
            "has_evidence": False,
            "available_tabs": [],
            "note": "no local evidence tree for this run_id",
        }
    else:
        meta = _trial_meta_from_evidence(evidence, run_id=rid, task_id=task_id, suite_row=suite_row)
        try:
            meta["evidence_relpath"] = str(evidence.resolve(strict=False).relative_to(root))
        except ValueError:
            meta["evidence_relpath"] = str(evidence)
        from bora.evidence.attempt_record import read_attempt_result

        result_preview = read_attempt_result(evidence)
        if result_preview and "metrics" in result_preview:
            metrics = result_preview.get("metrics")
            if isinstance(metrics, dict) and len(json.dumps(metrics)) > 8_000:
                result_preview = {**result_preview, "metrics": {"_truncated": True}}

    listed = list_task_trials(root, job_id, task_id)
    sibling_ids = [str(t.get("run_id")) for t in listed["trials"] if t.get("run_id")]
    if rid not in sibling_ids:
        sibling_ids.insert(0, rid)
    try:
        idx = sibling_ids.index(rid)
    except ValueError:
        idx = -1
    prev_id = sibling_ids[idx - 1] if idx > 0 else None
    next_id = sibling_ids[idx + 1] if 0 <= idx < len(sibling_ids) - 1 else None
    cmds = commands_for(root, task_id=task_id)

    return {
        "ok": True,
        "job": job,
        "task_id": task_id,
        "trial": meta,
        "result": result_preview,
        "prev_run_id": prev_id,
        "next_run_id": next_id,
        "sibling_run_ids": sibling_ids,
        "commands": cmds,
        "run_command": cmds.get("run_task") or cmds.get("run_suite"),
        "breadcrumb": [
            {"label": "Jobs", "href": "/"},
            {"label": job_id, "href": f"/jobs/{job_id}"},
            {"label": task_id, "href": f"/jobs/{job_id}/tasks/{task_id}"},
            {"label": rid, "href": None},
        ],
        "note": meta.get("note"),
    }
