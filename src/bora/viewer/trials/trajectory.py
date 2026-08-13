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

                # tool_call / observation: surface args & raw_output as content when needed
                args = obj.get("args")
                raw_output = obj.get("raw_output")
                if step_type == "tool_call" and content is None and args is not None:
                    try:
                        content = json.dumps(args, ensure_ascii=False)
                    except (TypeError, ValueError):
                        content = str(args)
                    if isinstance(content, str) and len(content) > 8_000:
                        content = content[:8_000] + "…[truncated]"
                if step_type == "observation" and content is None and raw_output is not None:
                    try:
                        content = json.dumps(raw_output, ensure_ascii=False)
                    except (TypeError, ValueError):
                        content = str(raw_output)
                    if isinstance(content, str) and len(content) > 8_000:
                        content = content[:8_000] + "…[truncated]"

                # permission_decision: decision summary (no tool payload secrets)
                if step_type == "permission_decision" and content is None:
                    parts: list[str] = []
                    for key in ("policy", "outcome", "option_id"):
                        val = obj.get(key)
                        if val is not None and val != "":
                            parts.append(f"{key}={val}")
                    if parts:
                        content = " · ".join(parts)

                # terminal: BORA invoke footer (ok / stop / usage / entry meta)
                if step_type == "terminal" and content is None:
                    tparts: list[str] = []
                    if obj.get("ok") is True:
                        tparts.append("ok")
                    elif obj.get("ok") is False:
                        tparts.append("not ok")
                    stop = obj.get("stop_reason")
                    if isinstance(stop, str) and stop:
                        tparts.append(f"stop={stop}")
                    err = obj.get("error")
                    if err is not None and err != "":
                        tparts.append(f"error={err}")
                    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else None
                    if usage:
                        try:
                            tparts.append(f"usage={json.dumps(usage, ensure_ascii=False)}")
                        except (TypeError, ValueError):
                            tparts.append(f"usage={usage}")
                    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else None
                    if meta:
                        # Compact interesting keys only
                        bits = []
                        for k in (
                            "executor_kind",
                            "acp_entry_id",
                            "actual_model",
                            "locked_model",
                            "protocol_version",
                        ):
                            if k in meta and meta[k] is not None:
                                bits.append(f"{k}={meta[k]}")
                        if bits:
                            tparts.append(" ".join(bits))
                    if tparts:
                        content = " · ".join(tparts)
                        if len(content) > 8_000:
                            content = content[:8_000] + "…[truncated]"

                steps.append(
                    {
                        "type": step_type,
                        "role": role,
                        "content": content,
                        "turn_index": obj.get("turn_index"),
                        "session_id": obj.get("session_id"),
                        "source": obj.get("source"),
                        "stop_reason": obj.get("stop_reason"),
                        "ok": obj.get("ok"),
                        "error": obj.get("error"),
                        "usage": obj.get("usage") if isinstance(obj.get("usage"), dict) else None,
                        "metadata": obj.get("metadata")
                        if isinstance(obj.get("metadata"), dict)
                        else None,
                        # tool_call / observation fields (fail-open; unknown types ignore)
                        "tool_call_id": obj.get("tool_call_id"),
                        "title": obj.get("title"),
                        "function_name": obj.get("function_name"),
                        "kind": obj.get("kind"),
                        "status": obj.get("status"),
                        "args": args if isinstance(args, (dict, list, str)) else None,
                        "raw_output": raw_output
                        if isinstance(raw_output, (dict, list, str))
                        else None,
                        "elapsed_ms": (
                            obj.get("elapsed_ms")
                            if isinstance(obj.get("elapsed_ms"), (int, float))
                            and not isinstance(obj.get("elapsed_ms"), bool)
                            else None
                        ),
                        "started_at": obj.get("started_at")
                        if isinstance(obj.get("started_at"), str)
                        else None,
                        "ended_at": obj.get("ended_at")
                        if isinstance(obj.get("ended_at"), str)
                        else None,
                        # permission_decision summary fields
                        "outcome": obj.get("outcome"),
                        "option_id": obj.get("option_id"),
                        "policy": obj.get("policy"),
                        "line": line_no,
                    }
                )
    except OSError:
        return steps
    return steps
