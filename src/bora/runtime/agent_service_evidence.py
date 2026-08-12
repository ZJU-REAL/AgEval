"""Evidence helpers for ParentAgentService invokes.

Trajectory is observational only — never PASS authority.

When an extension graph is provided (#71 B), seal runs multi
``trajectory_collect`` → ``trajectory_enrich``, then writes trajectory.jsonl
from the chain payload (single Core writer), then optional ``trajectory_seal``
provide + ``evidence_extra``.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from bora.evidence.redaction import RedactionError

_LOG = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Drive async lifecycle helpers from sync seal path."""
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def map_error_status(error: str | None) -> str:
    if not error:
        return "failed"
    if error in {"TimeoutExpired", "timeout"}:
        return "timeout"
    if error in {"CancelledError", "cancelled", "KeyboardInterrupt"}:
        return "cancelled"
    if error in {"offline_forced", "codex_binary_missing", "missing_credential"}:
        return "failed"
    if error.startswith("exit_"):
        return "failed"
    return "failed"


def seal_failure(
    handle: Any,
    *,
    status: str,
    error: str,
    latency_ms: float,
) -> None:
    if handle is None:
        return
    with contextlib.suppress(RedactionError):
        handle.seal(
            status=status,
            final_response=None,
            error=error,
            latency_ms=latency_ms,
        )


def write_invoke_request(
    handle: Any,
    *,
    prompt: str,
    profile_id: str,
    kind: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    acp_entry_id: str | None,
    actor_id: str | None,
    target_id: str | None,
    generation: int | None,
    l1_container_only: bool,
) -> None:
    """Write request.json + invoke_start lifecycle event. Raises RedactionError."""
    req_doc: dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "profile_id": profile_id,
        "executor_kind": kind,
        "model": model,
        "schema_hint": None,
        "tool_specs": [],
    }
    # Locator/name only — never secret values.
    if base_url:
        req_doc["base_url"] = base_url
    if api_key:
        req_doc["api_key"] = api_key
    if acp_entry_id:
        req_doc["acp_entry_id"] = acp_entry_id
    if actor_id:
        req_doc["actor_id"] = actor_id
    if target_id:
        req_doc["target_id"] = target_id
    if generation is not None:
        req_doc["generation"] = generation
    handle.write_request(req_doc)
    handle.append_event(
        {
            "type": "lifecycle",
            "phase": "invoke_start",
            "source": "agent_service",
            **({"execution_location": "attempt-container"} if l1_container_only else {}),
            **({"actor_id": actor_id} if actor_id else {}),
            **({"target_id": target_id} if target_id else {}),
        }
    )


def seal_invoke_result(
    handle: Any,
    *,
    result: Any,
    prompt: str,
    kind: str,
    turn_index: int,
    latency_ms: float,
    extension_graph: Any | None = None,
    extension_ctx: Any | None = None,
) -> str | None:
    """Stream events, write trajectory.jsonl for every executor, seal handle.

    When *extension_graph* is set (#71 B), runs ``trajectory_collect`` →
    ``trajectory_enrich`` on a live payload, writes from that payload, then
    ``trajectory_seal`` provide + ``evidence_extra``. Trajectory extension
    failures fail-open so the base write still succeeds (never invent PASS).

    Returns ``\"redaction_failed\"`` on RedactionError, else None.
    """
    # Stream backend events into invocation events.jsonl.
    events = getattr(result, "events", ()) or ()
    for ev in events:
        if isinstance(ev, dict):
            handle.append_event(ev)
    stderr = getattr(result, "stderr", "") or ""
    if stderr:
        handle.write_stderr(stderr)
    # Source refs as events (digests only — paths are under evidence root).
    for ref in getattr(result, "source_refs", ()) or ():
        if isinstance(ref, dict):
            handle.append_event(
                {
                    "type": "source_ref",
                    "kind": ref.get("kind"),
                    "digest": ref.get("digest"),
                    "source": "executor",
                }
            )

    # Training trajectory: turn-level (one invoke = one turn unit).
    # All executors write trajectory.jsonl (Viewer/Hub read path). ACP folds
    # session stream events into tool steps; non-ACP (e.g. nooa) still gets
    # user + assistant(final_text) + terminal from the same writer.
    meta = getattr(result, "metadata", None)
    meta = {} if not isinstance(meta, dict) else dict(meta)
    meta.setdefault("turn_index", turn_index)
    meta.setdefault("executor_kind", kind)

    traj_payload: dict[str, Any] = {
        "prompt": prompt,
        "events": tuple(events) if not isinstance(events, tuple) else events,
        "final_text": str(getattr(result, "text", "") or ""),
        "structured": (
            result.structured if isinstance(getattr(result, "structured", None), dict) else None
        ),
        "usage": getattr(result, "usage", None),
        "ok": bool(result.ok),
        "error": result.error,
        "metadata": meta,
    }

    if extension_graph is not None:
        try:
            from bora.plugins.lifecycle import (
                call_trajectory_seal,
                collect_evidence_extra,
                collect_trajectory,
                enrich_trajectory,
            )

            traj_payload = _run_async(
                collect_trajectory(extension_graph, traj_payload, ctx=extension_ctx)
            )
            if not isinstance(traj_payload, dict):
                traj_payload = {"prompt": prompt, "events": events, "metadata": meta}
            traj_payload = _run_async(
                enrich_trajectory(extension_graph, traj_payload, ctx=extension_ctx)
            )
            if not isinstance(traj_payload, dict):
                traj_payload = {"prompt": prompt, "events": events, "metadata": meta}
            sealed = _run_async(
                call_trajectory_seal(extension_graph, traj_payload, ctx=extension_ctx)
            )
            if isinstance(sealed, dict):
                traj_payload = sealed
                sm = traj_payload.get("seal_marker")
                if isinstance(sm, dict):
                    md = dict(traj_payload.get("metadata") or {})
                    md.setdefault("trajectory_seal", sm)
                    traj_payload["metadata"] = md
            extras = _run_async(collect_evidence_extra(extension_graph, [], ctx=extension_ctx))
            if isinstance(extras, list) and extras:
                extra_path = Path(handle.directory) / "evidence_extra.jsonl"
                with extra_path.open("w", encoding="utf-8") as fh:
                    for row in extras:
                        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        except Exception:
            # Trajectory extension must not invent PASS; fail open to base write.
            _LOG.exception("trajectory extension chain failed (fail-open)")

    from bora.adapters.acp import write_trajectory_jsonl

    sentinels = ()
    store = getattr(handle, "store", None)
    if store is not None:
        sentinels = tuple(getattr(store, "sentinels", ()) or ())

    write_prompt = str(traj_payload.get("prompt") if isinstance(traj_payload, dict) else prompt)
    write_events = traj_payload.get("events", events) if isinstance(traj_payload, dict) else events
    if not isinstance(write_events, (tuple, list)):
        write_events = events
    write_final = str(
        traj_payload.get("final_text", getattr(result, "text", "") or "")
        if isinstance(traj_payload, dict)
        else (getattr(result, "text", "") or "")
    )
    write_meta = (
        dict(traj_payload.get("metadata") or meta) if isinstance(traj_payload, dict) else meta
    )
    write_structured = (
        traj_payload.get("structured")
        if isinstance(traj_payload, dict)
        else getattr(result, "structured", None)
    )
    if not isinstance(write_structured, dict):
        write_structured = (
            result.structured if isinstance(getattr(result, "structured", None), dict) else None
        )
    write_usage = (
        traj_payload.get("usage")
        if isinstance(traj_payload, dict)
        else getattr(result, "usage", None)
    )
    write_ok = (
        bool(traj_payload.get("ok", result.ok))
        if isinstance(traj_payload, dict)
        else bool(result.ok)
    )
    write_error = (
        traj_payload.get("error", result.error) if isinstance(traj_payload, dict) else result.error
    )

    write_trajectory_jsonl(
        handle.directory,
        prompt=write_prompt,
        events=tuple(write_events) if not isinstance(write_events, tuple) else write_events,
        final_text=write_final,
        structured=write_structured,
        usage=write_usage if isinstance(write_usage, dict) else getattr(result, "usage", None),
        ok=write_ok,
        error=write_error
        if isinstance(write_error, str) or write_error is None
        else str(write_error),
        metadata=write_meta,
        redaction_sentinels=sentinels,
    )

    status = "completed" if result.ok else map_error_status(result.error)
    try:
        if result.ok:
            final = {
                "content": (result.text or "")[-8000:],
                "structured_output": (
                    result.structured if isinstance(result.structured, dict) else None
                ),
                "usage": getattr(result, "usage", None),
                "session": {
                    "reusable": False,
                    "handle": None,
                    "note": "ephemeral; no reusable session secret",
                },
            }
            seal_marker = (
                traj_payload.get("seal_marker") if isinstance(traj_payload, dict) else None
            )
            if isinstance(seal_marker, dict):
                final["trajectory_seal"] = seal_marker
            handle.seal(
                status="completed",
                final_response=final,
                latency_ms=latency_ms,
            )
        else:
            handle.seal(
                status=status,
                final_response=None,
                error=result.error,
                latency_ms=latency_ms,
            )
    except RedactionError:
        return "redaction_failed"
    return None
