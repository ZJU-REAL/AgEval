"""Evidence helpers for ParentAgentService invokes.

Trajectory is observational only — never PASS authority.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from ageval.evidence.redaction import RedactionError

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
    if error in {
        "offline_forced",
        "codex_binary_missing",
        "missing_credential",
        "credential_missing",
    }:
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
    actor_id: str | None = None,
) -> None:
    """Write request.json + invoke_start lifecycle event. Raises RedactionError."""
    request: dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "profile_id": profile_id,
        "executor_kind": kind,
        "model": model,
    }
    if actor_id:
        request["actor_id"] = actor_id
    handle.write_request(request)
    handle.append_event(
        {
            "type": "lifecycle",
            "phase": "invoke_start",
            "source": "agent_service",
            **({"actor_id": actor_id} if actor_id else {}),
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
    """Stream events, write trajectory.jsonl, then seal the invocation.

    The ``trajectory_collect`` → ``trajectory_enrich`` chains may shape the
    payload; the write itself stays here so the engine remains the only author
    of evidence. Returns ``"redaction_failed"`` on RedactionError, else None.
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
        traj_payload = _shape_trajectory(extension_graph, extension_ctx, traj_payload)

    from ageval.evidence.trajectory import write_trajectory_jsonl

    store = getattr(handle, "store", None)
    sentinels = tuple(getattr(store, "sentinels", ()) or ()) if store is not None else ()
    payload_events = traj_payload["events"]

    write_trajectory_jsonl(
        handle.directory,
        prompt=str(traj_payload["prompt"]),
        events=tuple(payload_events),
        final_text=str(traj_payload["final_text"]),
        structured=traj_payload["structured"],
        usage=traj_payload["usage"],
        ok=bool(traj_payload["ok"]),
        error=traj_payload["error"],
        metadata=dict(traj_payload["metadata"]),
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
            seal_marker = traj_payload.get("seal_marker")
            if isinstance(seal_marker, dict):
                final["trajectory_seal"] = seal_marker
            handle.seal(
                status="completed",
                final_response=final,
                latency_ms=latency_ms,
            )
        else:
            detail = None
            res_meta = getattr(result, "metadata", None)
            if isinstance(res_meta, dict):
                raw_detail = res_meta.get("error_detail")
                if isinstance(raw_detail, str) and raw_detail.strip():
                    detail = raw_detail.strip()
            handle.seal(
                status=status,
                final_response=None,
                error=result.error,
                latency_ms=latency_ms,
                error_detail=detail,
            )
    except RedactionError:
        return "redaction_failed"
    return None


def _shape_trajectory(
    extension_graph: Any,
    extension_ctx: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Let plugins shape the payload; the engine still writes the file.

    Observational only, so a broken chain leaves the engine's own payload
    standing rather than taking the invocation down.
    """
    from ageval.attempt.emit import run_chain
    from ageval.plugins.slots import TRAJECTORY_COLLECT, TRAJECTORY_ENRICH

    shaped = payload
    for slot in (TRAJECTORY_COLLECT, TRAJECTORY_ENRICH):
        try:
            out = _run_async(run_chain(extension_graph, slot, shaped, ctx=extension_ctx))
        except Exception:
            _LOG.exception("trajectory chain %s failed (fail-open)", slot)
            continue
        if isinstance(out, dict) and out.keys() >= payload.keys():
            shaped = out
        else:
            _LOG.warning("trajectory chain %s returned an unusable payload; kept engine copy", slot)
    return shaped
