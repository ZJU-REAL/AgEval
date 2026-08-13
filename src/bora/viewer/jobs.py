"""Local job listing for the Database results viewer.

Jobs are suite runs under ``.bora/suite-runs/`` **and** single-task Attempts
under ``.bora/runs/`` or ``tasks/<id>/.bora/runs/`` in the opened Database.
No suite-level PASS authority — scores are observational aggregates only.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from bora.application.suite import (
    aggregate_task_metrics,
    ensure_suite_task_refs,
    task_refs_for_summary,
)
from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.evidence.locators import default_runs_root
from bora.viewer.browse import commands_for


def safe_id_segment(value: str, *, field: str) -> str:
    """Single path segment (job_id / task_id / run_id); reject traversal."""
    text = (value or "").strip()
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or ".." in text
        or text.startswith(".")
    ):
        raise ConfigError(
            "invalid_package",
            f"invalid {field}: {value!r}",
            location=field,
        )
    return text


def _suite_root(database_root: Path) -> Path:
    return database_root.expanduser().resolve(strict=False) / ".bora" / "suite-runs"


def _load_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            "invalid_package",
            f"unreadable suite summary: {exc}",
            location=str(path),
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            "invalid_package",
            "suite summary must be a JSON object",
            location=str(path),
        )
    return data


def _task_dicts(summary: dict[str, Any]) -> list[dict[str, Any]]:
    raw = summary.get("tasks")
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, dict)]


def _ensure_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = summary.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return metrics
    rows = _task_dicts(summary)
    if not rows:
        return {
            "pass_rate": 0.0,
            "mean_score": 0.0,
            "n_tasks": 0,
            "n_pass": 0,
            "n_fail": 0,
            "n_error": 0,
            "missing_score_as": 0.0,
        }
    return aggregate_task_metrics(rows)


def _ensure_task_refs(summary: dict[str, Any]) -> list[dict[str, Any]]:
    raw = summary.get("task_refs")
    existing = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else None
    refs = ensure_suite_task_refs(summary, existing_refs=existing)
    if refs:
        return refs
    return task_refs_for_summary(_task_dicts(summary))


def _attempt_dicts(summary: dict[str, Any]) -> list[dict[str, Any]]:
    raw = summary.get("attempts")
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict)]


def _attempts_for_task(summary: dict[str, Any], task_id: str) -> list[dict[str, Any]]:
    """This job's attempts for *task_id* (not other suite/single runs of the same task)."""
    rows = [
        a
        for a in _attempt_dicts(summary)
        if str(a.get("task_id") or "") == task_id and a.get("run_id")
    ]
    if rows:
        return rows
    for ref in _ensure_task_refs(summary):
        if str(ref.get("task_id") or "") != task_id:
            continue
        ids = ref.get("attempt_run_ids")
        if isinstance(ids, list) and ids:
            return [
                {
                    "task_id": task_id,
                    "run_id": str(rid).strip(),
                    "status": ref.get("status"),
                    "score": ref.get("score"),
                }
                for rid in ids
                if rid is not None and str(rid).strip()
            ]
        rid = str(ref.get("run_id") or "").strip()
        if rid:
            return [
                {
                    "task_id": task_id,
                    "run_id": rid,
                    "status": ref.get("status"),
                    "score": ref.get("score"),
                }
            ]
    return []


def _job_row(summary: dict[str, Any], *, suite_dir: Path, database_root: Path) -> dict[str, Any]:
    metrics = _ensure_metrics(summary)
    refs = _ensure_task_refs(summary)
    n_tasks = int(metrics.get("n_tasks") or len(refs) or 0)
    n_done = int(metrics.get("n_pass") or 0) + int(metrics.get("n_fail") or 0)
    # Trials fraction: completed / planned
    trials_done = (
        n_done
        if n_done
        else int(metrics.get("n_pass") or 0)
        + int(metrics.get("n_fail") or 0)
        + int(metrics.get("n_error") or 0)
    )
    if trials_done == 0 and n_tasks:
        trials_done = n_tasks  # full suite summary usually has all rows
        # Prefer counting actual refs
        trials_done = len(refs) if refs else n_tasks

    man = None
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(database_root)

    return {
        "job_id": str(summary.get("suite_run_id") or suite_dir.name),
        "job_name": str(summary.get("suite_run_id") or suite_dir.name),
        "source_kind": "suite",
        "source": str(
            summary.get("database_id") or (man.database_id if man else "") or database_root.name
        ),
        "database_id": summary.get("database_id") or (man.database_id if man else None),
        "database_version": summary.get("database_version") or (man.version if man else None),
        "agent_label": str(summary.get("agent_label") or ""),
        "model_label": str(summary.get("model_label") or ""),
        "provider_label": str(summary.get("provider_label") or ""),
        "environment": str(summary.get("environment") or "local"),
        "result": metrics.get("mean_score"),
        "pass_rate": metrics.get("pass_rate"),
        "mean_score": metrics.get("mean_score"),
        "metrics": metrics,
        "started": summary.get("created_at"),
        "duration": summary.get("duration"),
        "n_attempts": summary.get("n_attempts"),
        "trials_done": trials_done,
        "trials_total": n_tasks or len(refs),
        "exit_code": summary.get("exit_code"),
        "task_count": n_tasks or len(refs),
        "summary_path": str(suite_dir / "summary.json"),
        "note": summary.get("note") or "per-task evaluator verdicts only; no suite-level PASS",
    }


def _load_progress(suite_dir: Path) -> dict[str, Any] | None:
    path = suite_dir / "progress.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _suite_run_ids(items: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in items:
        jid = str(row.get("job_id") or "")
        if jid:
            ids.add(jid)
    return ids


def _referenced_run_ids(database_root: Path, suite_items: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    root = database_root.expanduser().resolve(strict=False)
    for row in suite_items:
        job_id = str(row.get("job_id") or "")
        if not job_id:
            continue
        try:
            summary = _load_summary(_suite_root(root) / job_id / "summary.json")
        except ConfigError:
            continue
        for ref in _ensure_task_refs(summary):
            rid = str(ref.get("run_id") or "").strip()
            if rid:
                ids.add(rid)
            extra = ref.get("attempt_run_ids")
            if isinstance(extra, list):
                for item in extra:
                    text = str(item or "").strip()
                    if text:
                        ids.add(text)
        for task in _task_dicts(summary):
            rid = str(task.get("run_id") or "").strip()
            if rid:
                ids.add(rid)
        for attempt in _attempt_dicts(summary):
            rid = str(attempt.get("run_id") or "").strip()
            if rid:
                ids.add(rid)
    return ids


def _iter_attempt_dirs(database_root: Path) -> list[tuple[str, Path]]:
    root = database_root.expanduser().resolve(strict=False)
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def _add(run_id: str, path: Path) -> None:
        if run_id in seen:
            return
        try:
            safe_id_segment(run_id, field="run_id")
        except ConfigError:
            return
        found.append((run_id, path))
        seen.add(run_id)

    db_runs = default_runs_root(root)
    if db_runs.is_dir():
        for child in db_runs.iterdir():
            if child.is_dir():
                _add(child.name, child)

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    tasks_dir = root / tasks_root_name
    if tasks_dir.is_dir():
        for task_dir in tasks_dir.iterdir():
            if not task_dir.is_dir():
                continue
            local = default_runs_root(task_dir)
            if not local.is_dir():
                continue
            for child in local.iterdir():
                if child.is_dir():
                    _add(child.name, child)
    return found


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _single_job_row(evidence: Path, *, run_id: str, database_root: Path) -> dict[str, Any]:
    from bora.evidence.attempt_record import read_attempt_result

    result = read_attempt_result(evidence) or {}
    lock = _read_json_object(evidence / "lock.json") or {}
    task_id = str(result.get("task_id") or lock.get("task_id") or "")
    status = str(result.get("status") or result.get("verdict") or "")
    score = result.get("score")
    started = result.get("created_at") or result.get("started_at")
    man = None
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(database_root)
    return {
        "job_id": run_id,
        "job_name": run_id,
        "source_kind": "single",
        "source": task_id or "single",
        "database_id": man.database_id if man else None,
        "database_version": man.version if man else None,
        "agent_label": str(lock.get("agent_label") or result.get("agent_label") or ""),
        "model_label": str(lock.get("model_label") or result.get("model_label") or ""),
        "provider_label": str(lock.get("provider_label") or result.get("provider_label") or ""),
        "environment": str(result.get("environment") or "local"),
        "result": score,
        "pass_rate": 1.0 if status.upper() == "PASS" else 0.0,
        "mean_score": score,
        "metrics": {"n_tasks": 1, "n_pass": 1 if status.upper() == "PASS" else 0},
        "started": started,
        "duration": result.get("duration"),
        "n_attempts": 1,
        "trials_done": 1,
        "trials_total": 1,
        "exit_code": result.get("exit_code"),
        "task_count": 1,
        "summary_path": str(evidence / "result.json"),
        "task_id": task_id,
        "status": status.upper() if status else None,
        "score": score,
        "run_id": run_id,
        "note": "single-task attempt; per-task evaluator verdicts only",
    }


def list_jobs(database_root: Path) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    suite_root = _suite_root(root)
    items: list[dict[str, Any]] = []
    if suite_root.is_dir():
        for child in sorted(suite_root.iterdir(), key=lambda p: p.name, reverse=True):
            if not child.is_dir():
                continue
            summary_path = child / "summary.json"
            if not summary_path.is_file():
                continue
            try:
                summary = _load_summary(summary_path)
            except ConfigError:
                continue
            items.append(_job_row(summary, suite_dir=child, database_root=root))

    claimed = _referenced_run_ids(root, items) | _suite_run_ids(items)
    for run_id, evidence in _iter_attempt_dirs(root):
        if run_id in claimed:
            continue
        items.append(_single_job_row(evidence, run_id=run_id, database_root=root))
    items.sort(key=lambda r: str(r.get("started") or r.get("job_id") or ""), reverse=True)

    try:
        man = load_database_manifest(root)
        database_id = man.database_id
        version = man.version
    except ConfigError:
        database_id = None
        version = None

    return {
        "ok": True,
        "database_id": database_id,
        "version": version,
        "root": str(root),
        "items": items,
        "count": len(items),
        "commands": commands_for(root),
    }


def get_job(database_root: Path, job_id: str) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    job_id = safe_id_segment(job_id, field="job_id")
    suite_dir = _suite_root(root) / job_id
    # Confine suite dir under database root
    suite_resolved = suite_dir.resolve(strict=False)
    try:
        suite_resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "job path escapes database sandbox",
            location=job_id,
        ) from exc
    summary_path = suite_dir / "summary.json"
    if not summary_path.is_file():
        return _get_single_job(root, job_id)
    summary = _load_summary(summary_path)
    job = _job_row(summary, suite_dir=suite_dir, database_root=root)
    progress = _load_progress(suite_dir)
    if progress is not None:
        job["progress"] = progress
    refs = _ensure_task_refs(summary)
    # Prefer full task rows when present (score/status/error)
    by_id: dict[str, dict[str, Any]] = {}
    for t in _task_dicts(summary):
        if t.get("task_id"):
            by_id[str(t["task_id"])] = t

    task_rows: list[dict[str, Any]] = []
    for ref in refs:
        tid = str(ref.get("task_id") or "")
        full = by_id.get(tid, {})
        status = str(full.get("status") or ref.get("status") or "")
        score = full.get("score") if full.get("score") is not None else ref.get("score")
        attempt_rows = _attempts_for_task(summary, tid)
        if not attempt_rows:
            rid = full.get("run_id") or ref.get("run_id")
            if rid:
                attempt_rows = [
                    {
                        "task_id": tid,
                        "run_id": rid,
                        "status": status,
                        "score": score,
                        "error": full.get("error"),
                        "exit_code": full.get("exit_code"),
                        "duration": full.get("duration"),
                    }
                ]
        attempt_run_ids = [
            str(a.get("run_id")).strip()
            for a in attempt_rows
            if a.get("run_id") and str(a.get("run_id")).strip()
        ]
        n_val = full.get("n") if full.get("n") is not None else ref.get("n")
        if n_val is None:
            n_val = len(attempt_run_ids) or None
        task_rows.append(
            {
                "task_id": tid,
                "status": status.upper() if status else None,
                "score": score,
                "run_id": attempt_run_ids[0]
                if attempt_run_ids
                else full.get("run_id") or ref.get("run_id"),
                "attempt_run_ids": attempt_run_ids,
                "attempts": attempt_rows,
                "error": full.get("error"),
                "exit_code": full.get("exit_code"),
                "agent_label": job.get("agent_label") or "",
                "model_label": job.get("model_label") or "",
                "provider_label": job.get("provider_label") or "",
                "dataset": job.get("source") or job.get("database_id"),
                "duration": full.get("duration"),
                "phase_timing": full.get("phase_timing"),
                "n": n_val,
                "c": full.get("c") if full.get("c") is not None else ref.get("c"),
            }
        )

    return {
        "ok": True,
        "job": job,
        "tasks": task_rows,
        "task_count": len(task_rows),
        "progress": progress,
        "commands": commands_for(root),
        "note": job.get("note"),
    }


def _get_single_job(root: Path, job_id: str) -> dict[str, Any]:
    evidence = None
    for rid, path in _iter_attempt_dirs(root):
        if rid == job_id:
            evidence = path
            break
    if evidence is None:
        raise ConfigError(
            "unknown_task",
            f"suite run not found: {job_id}",
            location=job_id,
        )
    job = _single_job_row(evidence, run_id=job_id, database_root=root)
    task_id = str(job.get("task_id") or "")
    task_rows = [
        {
            "task_id": task_id,
            "status": job.get("status"),
            "score": job.get("score"),
            "run_id": job_id,
            "attempt_run_ids": [job_id],
            "attempts": [
                {
                    "task_id": task_id,
                    "run_id": job_id,
                    "status": job.get("status"),
                    "score": job.get("score"),
                    "exit_code": job.get("exit_code"),
                    "duration": job.get("duration"),
                }
            ],
            "error": None,
            "exit_code": job.get("exit_code"),
            "agent_label": job.get("agent_label") or "",
            "model_label": job.get("model_label") or "",
            "provider_label": job.get("provider_label") or "",
            "dataset": job.get("source") or job.get("database_id"),
            "duration": job.get("duration"),
            "n": 1,
        }
    ]
    return {
        "ok": True,
        "job": job,
        "tasks": task_rows,
        "task_count": 1,
        "progress": None,
        "commands": commands_for(root, task_id=task_id or None),
        "note": job.get("note"),
    }


def get_job_task(database_root: Path, job_id: str, task_id: str) -> dict[str, Any]:
    task_id = safe_id_segment(task_id, field="task_id")
    job_payload = get_job(database_root, job_id)
    match = None
    for row in job_payload["tasks"]:
        if row.get("task_id") == task_id:
            match = row
            break
    if match is None:
        raise ConfigError(
            "unknown_task",
            f"task {task_id!r} not in suite run {job_id!r}",
            location=task_id,
        )

    root = database_root.expanduser().resolve(strict=False)
    cmds = commands_for(root, task_id=task_id)
    # One-liner re-run command for the task (or full suite)
    run_cmd = cmds.get("run_task") or cmds.get("run_suite")

    started = job_payload["job"].get("started")
    attempt_src = match.get("attempts")
    if not isinstance(attempt_src, list) or not attempt_src:
        rid = match.get("run_id")
        attempt_src = [
            {
                "run_id": rid,
                "status": match.get("status"),
                "score": match.get("score"),
                "error": match.get("error"),
                "exit_code": match.get("exit_code"),
                "duration": match.get("duration"),
            }
        ]
        if not rid:
            attempt_src = []
    trials_out: list[dict[str, Any]] = []
    for row in attempt_src:
        if not isinstance(row, dict):
            continue
        rid = row.get("run_id") or match.get("run_id")
        if not rid:
            continue
        score = row.get("score") if row.get("score") is not None else match.get("score")
        trials_out.append(
            {
                "trial_id": rid,
                "task_id": task_id,
                "status": row.get("status") or match.get("status"),
                "reward": score,
                "score": score,
                "duration": row.get("duration") or match.get("duration"),
                "started": row.get("started") or started,
                "error": row.get("error") if row.get("error") is not None else match.get("error"),
                "run_id": rid,
                "exit_code": row.get("exit_code")
                if row.get("exit_code") is not None
                else match.get("exit_code"),
                "attempt_index": row.get("attempt_index"),
            }
        )

    return {
        "ok": True,
        "job": job_payload["job"],
        "task": match,
        "trials": trials_out,
        "agent_label": match.get("agent_label") or job_payload["job"].get("agent_label"),
        "model_label": match.get("model_label") or job_payload["job"].get("model_label"),
        "provider_label": match.get("provider_label") or job_payload["job"].get("provider_label"),
        "dataset": match.get("dataset") or job_payload["job"].get("source"),
        "commands": cmds,
        "run_command": run_cmd,
        "breadcrumb": [
            {"label": "Jobs", "href": "/"},
            {"label": job_id, "href": f"/jobs/{job_id}"},
            {"label": task_id, "href": None},
        ],
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
