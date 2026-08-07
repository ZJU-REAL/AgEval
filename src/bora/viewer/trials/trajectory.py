"""Trajectory read APIs for viewer trials (observational, not PASS)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora.viewer.jobs import get_job, safe_id_segment
from bora.viewer.trials.constants import MAX_JSONL_LINE, MAX_TRAJECTORY_STEPS
from bora.viewer.trials.paths import (
    _read_json_object,
    _safe_run_id,
    resolve_evidence_root,
)


def trial_trajectory(
    database_root: Path,
    job_id: str,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    get_job(root, job_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)
    inv_root = evidence / "agent" / "invocations"
    steps: list[dict[str, Any]] = []
    invocations: list[dict[str, Any]] = []
    truncated = False

    if inv_root.is_dir():
        inv_dirs = sorted(
            [p for p in inv_root.iterdir() if p.is_dir()],
            key=lambda p: p.name,
        )
        for inv in inv_dirs:
            inv_meta = _read_json_object(inv / "metadata.json") or {}
            traj_path = inv / "trajectory.jsonl"
            inv_steps: list[dict[str, Any]] = []
            if traj_path.is_file():
                inv_steps = _parse_trajectory_jsonl(traj_path)
            profile_id = inv_meta.get("profile_id")
            for step in inv_steps:
                if len(steps) >= MAX_TRAJECTORY_STEPS:
                    truncated = True
                    break
                steps.append(
                    {
                        **step,
                        "invocation": inv.name,
                        "invocation_id": inv_meta.get("invocation_id") or inv.name,
                        "profile_id": profile_id,
                        "model": inv_meta.get("model") or inv_meta.get("locked_model"),
                    }
                )
            invocations.append(
                {
                    "dirname": inv.name,
                    "invocation_id": inv_meta.get("invocation_id") or inv.name,
                    "profile_id": profile_id,
                    "executor_kind": inv_meta.get("executor_kind"),
                    "model": inv_meta.get("model") or inv_meta.get("locked_model"),
                    "status": inv_meta.get("status"),
                    "latency_ms": inv_meta.get("latency_ms"),
                    "step_count": len(inv_steps),
                    "has_trajectory": traj_path.is_file(),
                }
            )
            if truncated:
                break

    return {
        "ok": True,
        "run_id": rid,
        "task_id": task_id,
        "steps": steps,
        "step_count": len(steps),
        "invocations": invocations,
        "truncated": truncated,
        "note": None,
    }


def _parse_trajectory_jsonl(path: Path) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
                if len(steps) >= MAX_TRAJECTORY_STEPS:
                    break
                raw = line.strip()
                if not raw:
                    continue
                if len(raw) > MAX_JSONL_LINE:
                    raw = raw[:MAX_JSONL_LINE]
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    steps.append(
                        {
                            "type": "parse_error",
                            "line": line_no,
                            "content": raw[:500],
                        }
                    )
                    continue
                if not isinstance(obj, dict):
                    steps.append({"type": "raw", "line": line_no, "content": str(obj)[:500]})
                    continue
                role = obj.get("role")
                step_type = obj.get("type") or ("turn" if role else "event")
                content = obj.get("content")
                if content is not None and not isinstance(content, str):
                    try:
                        content = json.dumps(content, ensure_ascii=False)
                    except (TypeError, ValueError):
                        content = str(content)
                if isinstance(content, str) and len(content) > 8_000:
                    content = content[:8_000] + "…[truncated]"
                steps.append(
                    {
                        "type": step_type,
                        "role": role,
                        "content": content,
                        "turn_index": obj.get("turn_index"),
                        "source": obj.get("source"),
                        "stop_reason": obj.get("stop_reason"),
                        "ok": obj.get("ok"),
                        "error": obj.get("error"),
                        "usage": obj.get("usage") if isinstance(obj.get("usage"), dict) else None,
                        "metadata": obj.get("metadata")
                        if isinstance(obj.get("metadata"), dict)
                        else None,
                        "line": line_no,
                    }
                )
    except OSError:
        return steps
    return steps
