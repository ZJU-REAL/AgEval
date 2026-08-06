"""Database suite run: task_id-axis scheduling (Spec 22).

Orthogonal to Campaign (parameter matrix on one task). Application-layer only;
does not invent suite-level PASS.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bora.application.run_command import run_task
from bora.application.suite_metrics import aggregate_task_metrics, task_refs_for_summary
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
    suite_run_id: str = field(default_factory=lambda: f"suite_{uuid.uuid4().hex[:16]}")


def plan_suite_run(
    database_ref: str | Path,
    *,
    task_id: str | None = None,
    max_concurrent_tasks: int | None = None,
) -> SuitePlan:
    """Build a suite plan from Database root/ref and optional single-task filter."""
    root = resolve_database_root(database_ref)
    man = load_database_manifest(root)
    if task_id:
        # Validate membership via resolve path
        from bora.config.database import resolve_task

        resolve_task(root, task_id, manifest=man)
        ids = [task_id]
    else:
        ids = list_tasks(root, manifest=man)

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
    # Single-task mode: N is ignored (still ≥1 for pool size = 1 effectively).
    if len(ids) == 1:
        n = 1

    return SuitePlan(
        database_id=man.database_id,
        database_version=man.version,
        database_root=root,
        task_ids=ids,
        max_concurrent_tasks=n,
    )


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


async def _run_one(
    plan: SuitePlan,
    task_id: str,
    *,
    semaphore: asyncio.Semaphore,
    overrides: dict[str, Any] | None,
    run_fn: Callable[..., Awaitable[tuple[int, Any, dict[str, Any]]]],
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
            return {
                "task_id": task_id,
                "exit_code": code,
                "status": status,
                "score": getattr(result, "score", None),
                "metrics": dict(raw_metrics) if raw_metrics else {},
                "run_id": run_id,
                "digest": details.get("digest"),
                "error": None if code != 2 else (details.get("error") or status),
            }
        except ConfigError as exc:
            return {
                "task_id": task_id,
                "exit_code": 2,
                "status": "ERROR",
                "score": None,
                "metrics": {},
                "run_id": None,
                "digest": None,
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "task_id": task_id,
                "exit_code": 2,
                "status": "ERROR",
                "score": None,
                "metrics": {},
                "run_id": None,
                "digest": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            async with _inflight_lock:
                _inflight_current -= 1


async def execute_suite_run(
    plan: SuitePlan,
    *,
    overrides: dict[str, Any] | None = None,
    run_fn: Callable[..., Awaitable[tuple[int, Any, dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Execute all planned tasks with a concurrency pool; write suite summary."""
    reset_inflight_metrics()
    runner = run_fn or run_task
    semaphore = asyncio.Semaphore(plan.max_concurrent_tasks)
    tasks = [
        _run_one(plan, tid, semaphore=semaphore, overrides=overrides, run_fn=runner)
        for tid in plan.task_ids
    ]
    results = await asyncio.gather(*tasks)

    counts = {"pass": 0, "fail": 0, "error": 0, "skipped": 0}
    for row in results:
        st = str(row.get("status") or "").upper()
        if st == "PASS":
            counts["pass"] += 1
        elif st == "FAIL":
            counts["fail"] += 1
        else:
            counts["error"] += 1

    # Exit code matrix aligned with single-task bora run.
    if counts["error"] > 0:
        exit_code = 2
    elif counts["fail"] > 0:
        exit_code = 1
    else:
        exit_code = 0

    metrics = aggregate_task_metrics(results)
    summary: dict[str, Any] = {
        "schema": "bora.suite.summary/1",
        "suite_run_id": plan.suite_run_id,
        "database_id": plan.database_id,
        "database_version": plan.database_version,
        "max_concurrent_tasks": plan.max_concurrent_tasks,
        "task_ids": list(plan.task_ids),
        "tasks": list(results),
        "task_refs": task_refs_for_summary(results),
        "counts": counts,
        # Observational aggregates (leaderboard); never suite PASS authority.
        "metrics": metrics,
        "exit_code": exit_code,
        # UTC ISO-8601 (not unix epoch float).
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inflight_peak": get_inflight_peak(),
        # Explicitly NOT a suite PASS authority:
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }

    suite_dir = plan.database_root / ".bora" / "suite-runs" / plan.suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    out = suite_dir / "summary.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    summary["summary_path"] = str(out)
    return summary
