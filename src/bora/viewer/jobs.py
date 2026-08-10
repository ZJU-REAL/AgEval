"""Local suite-run (job) listing for the Database results viewer.

Jobs = ``.bora/suite-runs/<suite_run_id>/summary.json`` under a Database root.
No suite-level PASS authority — scores are observational aggregates only.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from bora.application.suite_metrics import aggregate_task_metrics, task_refs_for_summary
from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
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
    refs = summary.get("task_refs")
    if isinstance(refs, list) and refs:
        return [r for r in refs if isinstance(r, dict)]
    return task_refs_for_summary(_task_dicts(summary))


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
        raise ConfigError(
            "unknown_task",
            f"suite run not found: {job_id}",
            location=str(suite_dir),
        )
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
        task_rows.append(
            {
                "task_id": tid,
                "status": status.upper() if status else None,
                "score": score,
                "run_id": full.get("run_id") or ref.get("run_id"),
                "error": full.get("error"),
                "exit_code": full.get("exit_code"),
                "agent_label": job.get("agent_label") or "",
                "model_label": job.get("model_label") or "",
                "provider_label": job.get("provider_label") or "",
                "dataset": job.get("source") or job.get("database_id"),
                "duration": full.get("duration"),
                "phase_timing": full.get("phase_timing"),
                "n": full.get("n"),
                "c": full.get("c"),
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

    trial = {
        "trial_id": match.get("run_id") or f"{task_id}",
        "task_id": task_id,
        "status": match.get("status"),
        "reward": match.get("score"),
        "score": match.get("score"),
        "duration": match.get("duration"),
        "started": job_payload["job"].get("started"),
        "error": match.get("error"),
        "run_id": match.get("run_id"),
        "exit_code": match.get("exit_code"),
    }

    return {
        "ok": True,
        "job": job_payload["job"],
        "task": match,
        "trials": [trial],
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
