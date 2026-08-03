"""Parent-owned Agent Service: session bind + pre-spawn hard ceiling + trajectory.

Worker/SDK only holds an opaque session id and talks over a Unix socket.
Shared application code does not branch on benchmark/task names.
Each parent-bound invoke writes per-invocation evidence before returning.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import struct
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bora.evidence.redaction import RedactionError
from bora.evidence.store import AttemptEvidenceStore


@dataclass
class SessionBinding:
    session_id: str
    attempt_id: str
    profile_id: str
    model: str
    executor_kind: str
    closed: bool = False


@dataclass
class ParentAgentService:
    """Process-local parent authority for Agent invocations."""

    profiles: list[dict[str, Any]]
    agent_invocation_limit: int
    resolve_executor: Callable[..., Any]
    attempt_id: str  # Runtime-owned; never taken from Harness client
    offline_env: str = "BORA_OFFLINE_AGENT"
    evidence_store: AttemptEvidenceStore | None = None
    # Wall hard ceiling (monotonic seconds); checked before each external invoke.
    deadline_monotonic: float | None = None
    _remaining: int = field(init=False)
    _sessions: dict[str, SessionBinding] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    invocations_completed: int = 0

    def __post_init__(self) -> None:
        self._remaining = max(0, int(self.agent_invocation_limit))

    def _wall_expired(self) -> bool:
        return (
            self.deadline_monotonic is not None
            and time.monotonic() >= self.deadline_monotonic
        )

    def open_session(self, *, profile_id: str) -> dict[str, Any]:
        if self._wall_expired():
            return {"ok": False, "error": "wall_time_exceeded", "profile_id": profile_id}
        profile = next((p for p in self.profiles if p.get("id") == profile_id), None)
        if profile is None:
            return {"ok": False, "error": "unknown_profile", "profile_id": profile_id}
        with self._lock:
            sid = f"sess_{uuid.uuid4().hex[:16]}"
            binding = SessionBinding(
                session_id=sid,
                attempt_id=self.attempt_id,
                profile_id=profile_id,
                model=str(profile.get("model") or "gpt-5.4-mini"),
                executor_kind=str(profile.get("executor") or "codex"),
            )
            self._sessions[sid] = binding
            return {
                "ok": True,
                "session_id": sid,
                "profile_id": profile_id,
                "attempt_id": self.attempt_id,
                "provider_session_handle": None,
            }

    def invoke(self, *, session_id: str, prompt: str) -> dict[str, Any]:
        # Wall hard ceiling: refuse before external executor effect.
        if self._wall_expired():
            return {
                "ok": False,
                "error": "wall_time_exceeded",
                "text": "",
                "structured": None,
                "provider_session_handle": None,
            }
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": False, "error": "unknown_session"}
            if binding.closed:
                return {"ok": False, "error": "session_closed"}
            if binding.attempt_id != self.attempt_id:
                return {"ok": False, "error": "cross_attempt_session"}
            if self._remaining <= 0:
                return {"ok": False, "error": "agent_invocation_limit"}
            # Reserve before spawn (no refund on failure).
            self._remaining -= 1
            kind = binding.executor_kind
            model = binding.model
            profile_id = binding.profile_id

        handle = None
        started = time.monotonic()
        if self.evidence_store is not None:
            handle = self.evidence_store.begin_invocation(
                profile_id=profile_id,
                executor_kind=kind,
                model=model,
            )
            try:
                handle.write_request(
                    {
                        "messages": [{"role": "user", "content": prompt}],
                        "profile_id": profile_id,
                        "executor_kind": kind,
                        "model": model,
                        "schema_hint": None,
                        "tool_specs": [],
                    }
                )
                handle.append_event(
                    {
                        "type": "lifecycle",
                        "phase": "invoke_start",
                        "source": "agent_service",
                    }
                )
            except RedactionError:
                # Already sealed as redaction_failed by store.
                with self._lock:
                    self.invocations_completed += 1
                return {
                    "ok": False,
                    "error": "redaction_failed",
                    "model": model,
                    "text": "",
                    "structured": None,
                    "provider_session_handle": None,
                    "remaining_after": self._remaining,
                    "invocation_id": handle.invocation_id if handle else None,
                    "evidence_relative": handle.relative_path if handle else None,
                }

        try:
            executor = self.resolve_executor(kind, model=model)  # kind + model kwargs
        except KeyError:
            self._seal_failure(
                handle,
                status="failed",
                error="executor_unknown",
                latency_ms=(time.monotonic() - started) * 1000.0,
            )
            return {
                "ok": False,
                "error": "executor_unknown",
                "executor": kind,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }

        collect_dir = None
        if handle is not None:
            collect_dir = handle.directory / "backend_raw"
            collect_dir.mkdir(parents=True, exist_ok=True)

        # Mechanism test hook: force typed partial terminal on N-th invocation
        # (1-based). Values: crash | timeout | cancel | failed. Never invents PASS.
        force_err = os.environ.get("BORA_FORCE_INVOCATION_ERROR", "").strip()
        force_n = os.environ.get("BORA_FORCE_INVOCATION_N", "2").strip()
        try:
            force_at = int(force_n)
        except ValueError:
            force_at = 2
        next_n = self.invocations_completed + 1
        if force_err and next_n == force_at:
            latency = (time.monotonic() - started) * 1000.0
            status = _map_error_status(force_err if force_err != "crash" else "crash")
            if force_err == "crash":
                status = "crash"
            if handle is not None:
                handle.append_event(
                    {
                        "type": "lifecycle",
                        "phase": status,
                        "source": "force_hook",
                        "forced": force_err,
                    }
                )
                if force_err == "crash":
                    self._seal_failure(
                        handle, status="crash", error="forced_crash", latency_ms=latency
                    )
                else:
                    allowed = {"timeout", "cancelled", "failed", "crash"}
                    seal_status = status if status in allowed else "failed"
                    self._seal_failure(
                        handle,
                        status=seal_status,
                        error=f"forced_{force_err}",
                        latency_ms=latency,
                    )
            with self._lock:
                self.invocations_completed += 1
            return {
                "ok": False,
                "error": f"forced_{force_err}",
                "model": model,
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "remaining_after": self._remaining,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }

        sentinels = tuple(self.evidence_store.sentinels) if self.evidence_store else ()
        try:
            # Multi-invoke sessions need headroom beyond the codex default 45s.
            try:
                result = executor.invoke(
                    prompt,
                    timeout=300.0,
                    collect_dir=collect_dir,
                    redaction_sentinels=sentinels,
                )
            except TypeError:
                try:
                    result = executor.invoke(prompt, timeout=300.0, collect_dir=collect_dir)
                except TypeError:
                    try:
                        result = executor.invoke(prompt, timeout=300.0)
                    except TypeError:
                        result = executor.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 — executor crash must leave partial evidence
            latency = (time.monotonic() - started) * 1000.0
            if handle is not None:
                handle.append_event(
                    {
                        "type": "lifecycle",
                        "phase": "crash",
                        "error_type": type(exc).__name__,
                        "source": "agent_service",
                    }
                )
                self._seal_failure(
                    handle,
                    status="crash",
                    error=type(exc).__name__,
                    latency_ms=latency,
                )
            with self._lock:
                self.invocations_completed += 1
            return {
                "ok": False,
                "error": type(exc).__name__,
                "model": model,
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "remaining_after": self._remaining,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }

        latency = (time.monotonic() - started) * 1000.0
        if handle is not None:
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

            status = "completed" if result.ok else _map_error_status(result.error)
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
                        latency_ms=latency,
                    )
                else:
                    handle.seal(
                        status=status,
                        final_response=None,
                        error=result.error,
                        latency_ms=latency,
                    )
            except RedactionError:
                with self._lock:
                    self.invocations_completed += 1
                return {
                    "ok": False,
                    "error": "redaction_failed",
                    "model": result.model,
                    "text": "",
                    "structured": None,
                    "provider_session_handle": None,
                    "remaining_after": self._remaining,
                    "invocation_id": handle.invocation_id,
                    "evidence_relative": handle.relative_path,
                }

        with self._lock:
            self.invocations_completed += 1
        return {
            "ok": bool(result.ok),
            "error": result.error,
            "model": result.model,
            "text": (result.text or "")[-4000:],
            "structured": result.structured if isinstance(result.structured, dict) else None,
            "provider_session_handle": None,
            "remaining_after": self._remaining,
            "invocation_id": handle.invocation_id if handle else None,
            "evidence_relative": handle.relative_path if handle else None,
        }

    def close_session(self, *, session_id: str) -> dict[str, Any]:
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": True, "already": "missing"}
            binding.closed = True
            return {"ok": True}

    def _seal_failure(
        self,
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


def _map_error_status(error: str | None) -> str:
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


def _recv_msg(conn: socket.socket) -> dict[str, Any]:
    hdr = _read_exact(conn, 4)
    (n,) = struct.unpack("!I", hdr)
    if n > 4_000_000:
        raise ValueError("frame too large")
    body = _read_exact(conn, n)
    return json.loads(body.decode("utf-8"))


def _send_msg(conn: socket.socket, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    conn.sendall(struct.pack("!I", len(raw)) + raw)


def _read_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError("socket closed")
        buf += chunk
    return buf


class AgentServiceServer:
    """Unix-socket server exposing ParentAgentService to the task worker."""

    def __init__(self, service: ParentAgentService, sock_path: Path) -> None:
        self.service = service
        self.sock_path = sock_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def start(self) -> None:
        if self.sock_path.exists():
            self.sock_path.unlink()
        self.sock_path.parent.mkdir(parents=True, exist_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(self.sock_path))
        srv.listen(8)
        srv.settimeout(0.5)
        self._server = srv
        self._thread = threading.Thread(target=self._loop, name="bora-agent-service", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._server is not None:
            with contextlib.suppress(OSError):
                self._server.close()
        if self.sock_path.exists():
            with contextlib.suppress(OSError):
                self.sock_path.unlink()

    def _loop(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                with conn:
                    req = _recv_msg(conn)
                    resp = self._handle(req)
                    _send_msg(conn, resp)
            except Exception as exc:  # noqa: BLE001
                with contextlib.suppress(Exception):
                    _send_msg(
                        conn,
                        {
                            "ok": False,
                            "error": type(exc).__name__,
                            "message": str(exc),
                        },
                    )

    def _handle(self, req: dict[str, Any]) -> dict[str, Any]:
        op = req.get("op")
        if op == "open":
            # Client-supplied attempt_id is ignored; parent binding is authoritative.
            return self.service.open_session(profile_id=str(req.get("profile_id") or ""))
        if op == "invoke":
            return self.service.invoke(
                session_id=str(req.get("session_id") or ""),
                prompt=str(req.get("prompt") or ""),
            )
        if op == "close":
            return self.service.close_session(session_id=str(req.get("session_id") or ""))
        return {"ok": False, "error": "unknown_op"}


def agent_service_client_call(sock_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """SDK/worker client helper."""
    if os.environ.get("BORA_OFFLINE_AGENT") == "1" and payload.get("op") == "invoke":
        return {"ok": False, "error": "offline_forced", "structured": None}
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(sock_path)
        _send_msg(conn, payload)
        return _recv_msg(conn)
    finally:
        conn.close()
