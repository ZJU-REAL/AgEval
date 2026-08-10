"""Database suite run: task_id-axis scheduling (+ multi-attempt Always-k, #47).

Orthogonal to Campaign (parameter matrix on one task). Application-layer only;
does not invent suite-level PASS.

``n_attempts`` / k-attempt and resume are **CLI / job** parameters only — never
package identity or ``config_fingerprint`` inputs.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bora.application.run_command import run_task
from bora.application.suite_config_fingerprint import collect_suite_config
from bora.application.suite_metrics import (
    aggregate_k_metrics,
    aggregate_task_metrics,
    flatten_legacy_tasks_as_attempts,
    task_refs_for_summary,
)
from bora.config.database import list_tasks, load_database_manifest
from bora.config.errors import ConfigError
from bora.registry.resolve import resolve_database_root

# Instrumentation for tests: peaks concurrent in-flight workers.
_inflight_lock = asyncio.Lock()
_inflight_current = 0
_inflight_peak = 0


def reset_inflight_metrics() -> None:
    global _inflight_current, _inflight_peak
    _inflight_current = 0
    _inflight_peak = 0


def get_inflight_peak() -> int:
    return _inflight_peak


@dataclass
class SuitePlan:
    database_id: str
    database_version: str
    database_root: Path
    task_ids: list[str]
    max_concurrent_tasks: int
    n_attempts: int = 1
    suite_run_id: str = field(default_factory=lambda: f"suite_{uuid.uuid4().hex[:16]}")


def plan_suite_run(
    database_ref: str | Path,
    *,
    task_id: str | None = None,
    max_concurrent_tasks: int | None = None,
    n_attempts: int | None = None,
    suite_run_id: str | None = None,
) -> SuitePlan:
    """Build a suite plan from Database root/ref and optional single-task filter.

    Parameters
    ----------
    n_attempts:
        Always-k sample budget per task (CLI / job only). Default 1.
        Does **not** change package identity or fingerprint.
    suite_run_id:
        When resuming, reuse an existing suite run id.
    """
    root = resolve_database_root(database_ref)
    man = load_database_manifest(root)
    if task_id:
        # Validate membership via resolve path
        from bora.config.database import resolve_task

        resolve_task(root, task_id, manifest=man)
        ids = [task_id]
    else:
        ids = list_tasks(root, manifest=man)

    k = 1 if n_attempts is None else n_attempts
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ConfigError(
            "invalid_override",
            "n_attempts must be an integer ≥ 1",
            location="--n-attempts",
        )

    n = max_concurrent_tasks
    if n is None:
        if man.defaults and man.defaults.max_concurrent_tasks is not None:
            n = man.defaults.max_concurrent_tasks
        else:
            n = 1
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ConfigError(
            "invalid_override",
            "max_concurrent_tasks must be an integer ≥ 1",
            location="--max-concurrent-tasks",
        )
    # Single unit (one task × one attempt): concurrency is irrelevant → force 1.
    # Multi-attempt or multi-task: keep pool size so parallel only speeds wall time.
    if len(ids) == 1 and k == 1:
        n = 1

    plan = SuitePlan(
        database_id=man.database_id,
        database_version=man.version,
        database_root=root,
        task_ids=ids,
        max_concurrent_tasks=n,
        n_attempts=k,
    )
    if suite_run_id is not None and str(suite_run_id).strip():
        plan.suite_run_id = str(suite_run_id).strip()
    return plan


def suite_summary_path(database_root: Path, suite_run_id: str) -> Path:
    return (
        database_root.expanduser().resolve(strict=False)
        / ".bora"
        / "suite-runs"
        / suite_run_id
        / "summary.json"
    )


def load_suite_summary(database_root: Path, suite_run_id: str) -> dict[str, Any]:
    """Load an existing suite ``summary.json`` or raise ConfigError."""
    path = suite_summary_path(database_root, suite_run_id)
    if not path.is_file():
        raise ConfigError(
            "suite_not_found",
            f"suite summary not found: {suite_run_id}",
            location=str(path),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            "suite_summary_invalid",
            f"cannot read suite summary: {exc}",
            location=str(path),
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            "suite_summary_invalid",
            "suite summary must be a JSON object",
            location=str(path),
        )
    return data


def extract_run_id(database_root: Path, *candidates: object) -> str | None:
    """Extract Attempt ``run_id`` (directory name under ``.bora/runs/``).

    Suite summary only stores ``run_id``; local path is always
    ``{database_root}/.bora/runs/{run_id}/``. Host absolute paths must not appear.
    """
    root = database_root.expanduser().resolve(strict=False)
    for raw in candidates:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        path = Path(text)
        name = path.name
        # Bare id, ``.bora/runs/<id>``, or ``.../runs/<id>``
        if (
            name.startswith("sha256_")
            and "_run_" in name
            and ("/" not in text.rstrip("/") or "runs" in path.parts or text.startswith(".bora/"))
        ):
            return name
        try:
            abs_path = path if path.is_absolute() else (root / path)
            abs_path = abs_path.resolve(strict=False)
            rel = abs_path.relative_to(root)
            parts = rel.parts
            if len(parts) >= 3 and parts[0] == ".bora" and parts[1] == "runs":
                return parts[2]
        except (ValueError, OSError):
            parts = path.parts
            if "runs" in parts:
                idx = parts.index("runs")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            if name.startswith("sha256_") and "_run_" in name:
                return name
    return None


def planned_units(plan: SuitePlan) -> list[tuple[str, int]]:
    """Expand Always-k units: ``(task_id, attempt_index)`` for index in ``0..k-1``."""
    return [(tid, i) for tid in plan.task_ids for i in range(plan.n_attempts)]


def _existing_attempt_keys(attempts: list[dict[str, Any]]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for row in attempts:
        tid = str(row.get("task_id") or "")
        idx = row.get("attempt_index")
        if not tid:
            continue
        if not isinstance(idx, int) or isinstance(idx, bool):
            idx = 0
        keys.add((tid, idx))
    return keys


async def _run_one(
    plan: SuitePlan,
    task_id: str,
    attempt_index: int,
    *,
    semaphore: asyncio.Semaphore,
    overrides: dict[str, Any] | None,
    run_fn: Callable[..., Awaitable[tuple[int, Any, dict[str, Any]]]],
    profiles_path: Path | str | None = None,
) -> dict[str, Any]:
    global _inflight_current, _inflight_peak
    async with semaphore:
        async with _inflight_lock:
            _inflight_current += 1
            _inflight_peak = max(_inflight_peak, _inflight_current)
        try:
            code, result, details = await run_fn(
                plan.database_root,
                task_id,
                overrides=overrides,
                profiles_path=profiles_path,
            )
            status = getattr(result, "status", None) or details.get("status") or "ERROR"
            run_id = extract_run_id(
                plan.database_root,
                getattr(result, "evidence_path", None),
                details.get("run_dir"),
                details.get("logs"),
                getattr(result, "logs", None),
            )
            raw_metrics = getattr(result, "metrics", None)
            if not isinstance(raw_metrics, dict):
                detail_metrics = details.get("metrics")
                raw_metrics = detail_metrics if isinstance(detail_metrics, dict) else {}
            phase_timing = details.get("phase_timing")
            if not isinstance(phase_timing, dict):
                phase_timing = None
            duration = None
            if phase_timing is not None:
                from bora.application.phase_timing import format_duration_ms

                duration = format_duration_ms(phase_timing.get("total_ms"))  # type: ignore[arg-type]
            return {
                "task_id": task_id,
                "attempt_index": attempt_index,
                "exit_code": code,
                "status": status,
                "score": getattr(result, "score", None),
                "metrics": dict(raw_metrics) if raw_metrics else {},
                "run_id": run_id,
                "digest": details.get("digest"),
                "error": None if code != 2 else (details.get("error") or status),
                "phase_timing": phase_timing,
                "duration": duration,
                "phase": "terminal",
            }
        except ConfigError as exc:
            return {
                "task_id": task_id,
                "attempt_index": attempt_index,
                "exit_code": 2,
                "status": "ERROR",
                "score": None,
                "metrics": {},
                "run_id": None,
                "digest": None,
                "error": str(exc),
                "phase_timing": None,
                "duration": None,
                "phase": "error",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "task_id": task_id,
                "attempt_index": attempt_index,
                "exit_code": 2,
                "status": "ERROR",
                "score": None,
                "metrics": {},
                "run_id": None,
                "digest": None,
                "error": f"{type(exc).__name__}: {exc}",
                "phase_timing": None,
                "duration": None,
                "phase": "error",
            }
        finally:
            async with _inflight_lock:
                _inflight_current -= 1


def suite_dir_for(plan: SuitePlan) -> Path:
    return plan.database_root / ".bora" / "suite-runs" / plan.suite_run_id


def cancel_request_path(database_root: Path, suite_run_id: str) -> Path:
    return (
        database_root.expanduser().resolve(strict=False)
        / ".bora"
        / "suite-runs"
        / suite_run_id
        / "cancel.requested"
    )


def is_suite_cancel_requested(database_root: Path, suite_run_id: str) -> bool:
    return cancel_request_path(database_root, suite_run_id).is_file()


def request_suite_cancel(database_root: Path, suite_run_id: str) -> Path:
    """Create cancel.requested so the suite loop stops starting new units."""
    path = cancel_request_path(database_root, suite_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "bora.suite.cancel/1",
                "suite_run_id": suite_run_id,
                "requested_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_suite_progress(
    plan: SuitePlan,
    *,
    done: int,
    total: int,
    running: list[dict[str, Any]],
    status: str = "running",
) -> None:
    """Job progress snapshot for viewer / status (D2)."""
    suite_dir = suite_dir_for(plan)
    suite_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": "bora.suite.progress/1",
        "suite_run_id": plan.suite_run_id,
        "status": status,
        "done": done,
        "total": total,
        "n_attempts": plan.n_attempts,
        "max_concurrent_tasks": plan.max_concurrent_tasks,
        "running": running,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cancel_requested": is_suite_cancel_requested(plan.database_root, plan.suite_run_id),
    }
    out = suite_dir / "progress.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)


ProgressCallback = Callable[[dict[str, Any]], None]


def _build_summary(
    plan: SuitePlan,
    attempts: list[dict[str, Any]],
    *,
    overrides: dict[str, Any] | None,
    profiles_path: Path | str | None,
) -> dict[str, Any]:
    """Roll attempts → tasks + metrics; write identity fields (no k in fingerprint)."""
    k_agg = aggregate_k_metrics(
        attempts,
        task_ids=plan.task_ids,
        n_attempts=plan.n_attempts,
    )
    task_rows: list[dict[str, Any]] = list(k_agg.pop("task_rows"))

    # Strip nested attempts from tasks[] for a flatter summary when k==1
    # (backward-compatible shape); keep attempts[] always for resume.
    tasks_out: list[dict[str, Any]]
    if plan.n_attempts == 1 and all(len(t.get("attempts") or []) <= 1 for t in task_rows):
        tasks_out = []
        for t in task_rows:
            nested = t.get("attempts") or []
            base = nested[0] if nested else {}
            row = {
                "task_id": t["task_id"],
                "exit_code": base.get("exit_code"),
                "status": t["status"],
                "score": base.get("score", t.get("score")),
                "metrics": base.get("metrics") if isinstance(base.get("metrics"), dict) else {},
                "run_id": t.get("run_id"),
                "digest": base.get("digest"),
                "error": base.get("error"),
                "attempt_index": 0,
                "phase_timing": base.get("phase_timing"),
                "duration": base.get("duration"),
            }
            # Surface k stats only when n_attempts was requested >1 historically;
            # for k==1 omit pass_at_k maps from task row to keep legacy tests green.
            tasks_out.append(row)
        metrics = aggregate_task_metrics(tasks_out)
        # Still attach pass@k maps under metrics when useful (k=1 → pass@1 = pass_rate).
        metrics["n_attempts"] = plan.n_attempts
        metrics["k_values"] = k_agg.get("k_values", [1])
        metrics["pass_at_k"] = k_agg.get("pass_at_k", {})
        metrics["pass_power_k"] = k_agg.get("pass_power_k", {})
        metrics["per_task"] = k_agg.get("per_task", [])
    else:
        tasks_out = []
        for t in task_rows:
            # Prefer first attempt's phase_timing for job-level display (observational).
            nested = t.get("attempts") or []
            first_pt = None
            first_dur = None
            if nested and isinstance(nested[0], Mapping):
                first_pt = nested[0].get("phase_timing")
                first_dur = nested[0].get("duration")
            tasks_out.append(
                {
                    "task_id": t["task_id"],
                    "status": t["status"],
                    "score": t["score"],
                    "n": t["n"],
                    "c": t["c"],
                    "run_id": t.get("run_id"),
                    "pass_at_k": t["pass_at_k"],
                    "pass_power_k": t["pass_power_k"],
                    "attempt_indices": t.get("attempt_indices"),
                    "phase_timing": first_pt,
                    "duration": first_dur,
                }
            )
        metrics = {
            "pass_rate": k_agg["pass_rate"],
            "mean_score": k_agg["mean_score"],
            "n_tasks": k_agg["n_tasks"],
            "n_pass": k_agg["n_pass"],
            "n_fail": k_agg["n_fail"],
            "n_error": k_agg["n_error"],
            "missing_score_as": k_agg["missing_score_as"],
            "n_attempts": plan.n_attempts,
            "k_values": k_agg["k_values"],
            "pass_at_k": k_agg["pass_at_k"],
            "pass_power_k": k_agg["pass_power_k"],
            "per_task": k_agg["per_task"],
        }

    counts = {"pass": 0, "fail": 0, "error": 0, "skipped": 0}
    for row in tasks_out:
        st = str(row.get("status") or "").upper()
        if st == "PASS":
            counts["pass"] += 1
        elif st == "FAIL":
            counts["fail"] += 1
        else:
            counts["error"] += 1

    if counts["error"] > 0:
        exit_code = 2
    elif counts["fail"] > 0:
        exit_code = 1
    else:
        exit_code = 0

    # Fingerprint from one row per task (first attempt's run_id if needed).
    fp_rows: list[dict[str, Any]] = []
    by_task_attempt: dict[str, list[dict[str, Any]]] = {}
    for a in attempts:
        tid = str(a.get("task_id") or "")
        by_task_attempt.setdefault(tid, []).append(a)
    for tid in plan.task_ids:
        rows = by_task_attempt.get(tid, [])
        pick = None
        for r in rows:
            if str(r.get("status") or "").upper() == "PASS" and r.get("run_id"):
                pick = r
                break
        if pick is None and rows:
            pick = rows[0]
        if pick is not None:
            fp_rows.append({"task_id": tid, "run_id": pick.get("run_id")})
        else:
            fp_rows.append({"task_id": tid, "run_id": None})

    config_fields = collect_suite_config(
        plan.database_root,
        fp_rows,
        overrides=overrides,
        task_ids=plan.task_ids,
        profiles_path=profiles_path,
    )

    summary: dict[str, Any] = {
        "schema": "bora.suite.summary/1",
        "suite_run_id": plan.suite_run_id,
        "database_id": plan.database_id,
        "database_version": plan.database_version,
        "max_concurrent_tasks": plan.max_concurrent_tasks,
        "n_attempts": plan.n_attempts,
        "task_ids": list(plan.task_ids),
        "attempts": list(attempts),
        "tasks": tasks_out,
        "task_refs": task_refs_for_summary(tasks_out),
        "counts": counts,
        # Observational aggregates (leaderboard / job stats); never suite PASS.
        "metrics": metrics,
        "exit_code": exit_code,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inflight_peak": get_inflight_peak(),
        "config_fingerprint": config_fields["config_fingerprint"],
        "config_homogeneous": config_fields["config_homogeneous"],
        "actors_summary": config_fields["actors_summary"],
        "agent_label": config_fields.get("agent_label") or "",
        "model_label": config_fields.get("model_label") or "",
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }
    if config_fields.get("job_overlay") is not None:
        summary["job_overlay"] = config_fields["job_overlay"]
    return summary


def _write_summary(plan: SuitePlan, summary: dict[str, Any]) -> dict[str, Any]:
    suite_dir = plan.database_root / ".bora" / "suite-runs" / plan.suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    out = suite_dir / "summary.json"
    tmp = out.with_suffix(".tmp")
    # summary_path is host-local; keep off the durable document? Historical
    # code put it only on the returned dict, not always on disk — write clean.
    disk = {k: v for k, v in summary.items() if k != "summary_path"}
    tmp.write_text(json.dumps(disk, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    summary["summary_path"] = str(out)
    return summary


async def execute_suite_run(
    plan: SuitePlan,
    *,
    overrides: dict[str, Any] | None = None,
    run_fn: Callable[..., Awaitable[tuple[int, Any, dict[str, Any]]]] | None = None,
    profiles_path: Path | str | None = None,
    resume: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Execute planned task×attempt units with a concurrency pool; write summary.

    When ``resume=True``, load existing attempts for ``plan.suite_run_id``, skip
    units that already finished, **append** new attempts, and recompute metrics.
    Existing attempt rows are never rewritten.

    Cancel (#47 D4): if ``suite-runs/<id>/cancel.requested`` appears, no new units
    start; in-flight units finish; remaining planned units get cancelled rows.
    """
    reset_inflight_metrics()
    runner = run_fn or run_task
    suite_dir_for(plan).mkdir(parents=True, exist_ok=True)

    existing: list[dict[str, Any]] = []
    if resume:
        old = load_suite_summary(plan.database_root, plan.suite_run_id)
        raw_attempts = old.get("attempts")
        if isinstance(raw_attempts, list) and raw_attempts:
            existing = [dict(a) for a in raw_attempts if isinstance(a, Mapping)]
        else:
            legacy_tasks = old.get("tasks")
            if isinstance(legacy_tasks, list):
                existing = flatten_legacy_tasks_as_attempts(
                    [t for t in legacy_tasks if isinstance(t, Mapping)]
                )
        # Prefer higher n_attempts if resume raises budget.
        old_k = old.get("n_attempts")
        if isinstance(old_k, int) and not isinstance(old_k, bool) and old_k > plan.n_attempts:
            # Keep caller's plan.n_attempts as target; old higher budget means
            # more existing keys — fine.
            pass

    done_keys = _existing_attempt_keys(existing)
    units = planned_units(plan)
    todo = [(tid, idx) for tid, idx in units if (tid, idx) not in done_keys]
    total_units = max(len(units), len(todo) + len(done_keys & set(units)))
    # Progress: completed existing + in-flight bookkeeping.
    completed_count = len(done_keys & set(units)) if resume else 0
    cancelled = False
    new_results: list[dict[str, Any]] = []
    skipped_cancelled: list[dict[str, Any]] = []

    def _emit(event: dict[str, Any]) -> None:
        if on_progress is not None:
            with contextlib.suppress(Exception):
                on_progress(event)

    _write_suite_progress(
        plan,
        done=completed_count,
        total=total_units,
        running=[],
        status="running" if todo else "complete",
    )
    _emit(
        {
            "type": "suite_start",
            "suite_run_id": plan.suite_run_id,
            "done": completed_count,
            "total": total_units,
            "todo": len(todo),
        }
    )

    # Worker pool: claim units by index so cancel can stop scheduling new work.
    todo_list = list(todo)
    claim_index = 0
    claim_lock = asyncio.Lock()
    worker_n = min(plan.max_concurrent_tasks, max(1, len(todo_list))) if todo_list else 0

    progress_lock = asyncio.Lock()
    inflight_labels: dict[tuple[str, int], str] = {}
    semaphore = asyncio.Semaphore(plan.max_concurrent_tasks)

    def _cancelled_row(tid: str, idx: int) -> dict[str, Any]:
        return {
            "task_id": tid,
            "attempt_index": idx,
            "exit_code": 2,
            "status": "ERROR",
            "score": None,
            "metrics": {},
            "run_id": None,
            "digest": None,
            "error": "suite_cancelled",
            "phase_timing": None,
            "duration": None,
            "phase": "cancelled",
        }

    async def _worker() -> None:
        nonlocal completed_count, cancelled, claim_index
        while True:
            if is_suite_cancel_requested(plan.database_root, plan.suite_run_id):
                cancelled = True
                return
            async with claim_lock:
                if claim_index >= len(todo_list):
                    return
                tid, idx = todo_list[claim_index]
                claim_index += 1
            if is_suite_cancel_requested(plan.database_root, plan.suite_run_id):
                cancelled = True
                async with progress_lock:
                    skipped_cancelled.append(_cancelled_row(tid, idx))
                    completed_count += 1
                return

            async with progress_lock:
                inflight_labels[(tid, idx)] = "running"
                _write_suite_progress(
                    plan,
                    done=completed_count,
                    total=total_units,
                    running=[
                        {"task_id": t, "attempt_index": i, "phase": ph}
                        for (t, i), ph in inflight_labels.items()
                    ],
                )
                _emit(
                    {
                        "type": "unit_start",
                        "task_id": tid,
                        "attempt_index": idx,
                        "done": completed_count,
                        "total": total_units,
                        "running": list(inflight_labels.keys()),
                    }
                )

            row = await _run_one(
                plan,
                tid,
                idx,
                semaphore=semaphore,
                overrides=overrides,
                run_fn=runner,
                profiles_path=profiles_path,
            )
            async with progress_lock:
                new_results.append(row)
                inflight_labels.pop((tid, idx), None)
                completed_count += 1
                cancel_now = is_suite_cancel_requested(plan.database_root, plan.suite_run_id)
                if cancel_now:
                    cancelled = True
                if cancel_now:
                    st = "cancelling"
                elif claim_index < len(todo_list) or inflight_labels:
                    st = "running"
                else:
                    st = "complete"

                _write_suite_progress(
                    plan,
                    done=completed_count,
                    total=total_units,
                    running=[
                        {"task_id": t, "attempt_index": i, "phase": ph}
                        for (t, i), ph in inflight_labels.items()
                    ],
                    status=st,
                )
                _emit(
                    {
                        "type": "unit_done",
                        "task_id": tid,
                        "attempt_index": idx,
                        "status": row.get("status"),
                        "done": completed_count,
                        "total": total_units,
                        "duration": row.get("duration"),
                    }
                )

    if worker_n:
        await asyncio.gather(*[asyncio.create_task(_worker()) for _ in range(worker_n)])

    # Units never claimed because of cancel → synthetic cancelled rows.
    async with claim_lock:
        remaining = todo_list[claim_index:]
    if remaining:
        cancelled = True
        for tid, idx in remaining:
            skipped_cancelled.append(_cancelled_row(tid, idx))
            completed_count += 1
    if skipped_cancelled:
        new_results.extend(skipped_cancelled)

    # Append-only merge: existing first (stable), then new; never mutate old rows.
    attempts = list(existing) + new_results
    # Drop attempts outside planned task set only when filtering? Keep all that
    # belong to plan.task_ids; preserve other tasks already in the job for resume
    # of a subset (Harbor: re-run one task without wiping the rest).
    if resume and plan.task_ids:
        planned_set = set(plan.task_ids)
        # Keep attempts for tasks not in this plan's filter (other suite members).
        kept_other = [a for a in existing if str(a.get("task_id") or "") not in planned_set]
        # For planned tasks: existing matching keys + new
        planned_existing = [a for a in existing if str(a.get("task_id") or "") in planned_set]
        attempts = kept_other + planned_existing + new_results

    # Union task_ids for summary when resume brings siblings.
    if resume:
        all_ids: list[str] = []
        seen: set[str] = set()
        for tid in plan.task_ids:
            if tid not in seen:
                all_ids.append(tid)
                seen.add(tid)
        for a in attempts:
            tid = str(a.get("task_id") or "")
            if tid and tid not in seen:
                all_ids.append(tid)
                seen.add(tid)
        # Mutate a shallow copy of plan fields for summary only.
        summary_plan = SuitePlan(
            database_id=plan.database_id,
            database_version=plan.database_version,
            database_root=plan.database_root,
            task_ids=all_ids,
            max_concurrent_tasks=plan.max_concurrent_tasks,
            n_attempts=plan.n_attempts,
            suite_run_id=plan.suite_run_id,
        )
        # If other tasks had more samples, take max n_attempts for display budget.
        max_n = plan.n_attempts
        by_t: dict[str, int] = {}
        for a in attempts:
            tid = str(a.get("task_id") or "")
            by_t[tid] = by_t.get(tid, 0) + 1
        if by_t:
            max_n = max(max_n, max(by_t.values()))
        summary_plan.n_attempts = max_n
    else:
        summary_plan = plan

    summary = _build_summary(
        summary_plan,
        attempts,
        overrides=overrides,
        profiles_path=profiles_path,
    )
    if resume:
        summary["resumed"] = True
        summary["new_attempts"] = len([r for r in new_results if r.get("phase") != "cancelled"])
        summary["skipped_attempts"] = len(done_keys & set(units))
    if cancelled or is_suite_cancel_requested(plan.database_root, plan.suite_run_id):
        summary["cancelled"] = True
        summary["status"] = "cancelled"
        # Prefer non-zero exit when cancelled with incomplete work.
        if summary.get("exit_code") == 0 and skipped_cancelled:
            summary["exit_code"] = 2
        _write_suite_progress(
            plan,
            done=completed_count,
            total=total_units,
            running=[],
            status="cancelled",
        )
        _emit(
            {
                "type": "suite_cancelled",
                "suite_run_id": plan.suite_run_id,
                "done": completed_count,
                "total": total_units,
                "cancelled_units": len(skipped_cancelled),
            }
        )
    else:
        _write_suite_progress(
            plan,
            done=completed_count,
            total=total_units,
            running=[],
            status="complete",
        )
        _emit(
            {
                "type": "suite_complete",
                "suite_run_id": plan.suite_run_id,
                "done": completed_count,
                "total": total_units,
                "exit_code": summary.get("exit_code"),
            }
        )
    return _write_summary(plan, summary)
