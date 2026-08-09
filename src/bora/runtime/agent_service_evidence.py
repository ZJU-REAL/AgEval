"""Evidence helpers for ParentAgentService invokes.

Trajectory is observational only — never PASS authority.
"""

from __future__ import annotations

import contextlib
from typing import Any

from bora.evidence.redaction import RedactionError


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
) -> str | None:
    """Stream events, write trajectory (ACP), seal handle.

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
    # Prefer executor-written file; else synthesize. Stamp turn_index
    # from completed+1 (this invocation's 1-based seq within attempt).
    meta = getattr(result, "metadata", None)
    meta = {} if not isinstance(meta, dict) else dict(meta)
    meta.setdefault("turn_index", turn_index)
    is_acp = meta.get("executor_kind") == "acp" or kind == "acp"
    if is_acp:
        from bora.adapters.acp import write_trajectory_jsonl

        # Always rewrite with turn_index even if executor already wrote.
        sentinels = ()
        store = getattr(handle, "store", None)
        if store is not None:
            sentinels = tuple(getattr(store, "sentinels", ()) or ())
        write_trajectory_jsonl(
            handle.directory,
            prompt=prompt,
            events=tuple(events) if not isinstance(events, tuple) else events,
            final_text=str(getattr(result, "text", "") or ""),
            structured=(
                result.structured if isinstance(getattr(result, "structured", None), dict) else None
            ),
            usage=getattr(result, "usage", None),
            ok=bool(result.ok),
            error=result.error,
            metadata=meta,
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
