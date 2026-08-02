"""Parent-owned Agent Service: session bind + pre-spawn hard ceiling.

Worker/SDK only holds an opaque session id and talks over a Unix socket.
Shared application code does not branch on benchmark/task names.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


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
    resolve_executor: Callable[[str], Any]
    offline_env: str = "BORA_OFFLINE_AGENT"
    _remaining: int = field(init=False)
    _sessions: dict[str, SessionBinding] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    invocations_completed: int = 0

    def __post_init__(self) -> None:
        self._remaining = max(0, int(self.agent_invocation_limit))

    def open_session(self, *, attempt_id: str, profile_id: str) -> dict[str, Any]:
        profile = next((p for p in self.profiles if p.get("id") == profile_id), None)
        if profile is None:
            return {"ok": False, "error": "unknown_profile", "profile_id": profile_id}
        with self._lock:
            sid = f"sess_{uuid.uuid4().hex[:16]}"
            binding = SessionBinding(
                session_id=sid,
                attempt_id=attempt_id,
                profile_id=profile_id,
                model=str(profile.get("model") or "gpt-5.4-mini"),
                executor_kind=str(profile.get("executor") or "codex"),
            )
            self._sessions[sid] = binding
            return {
                "ok": True,
                "session_id": sid,
                "profile_id": profile_id,
                "provider_session_handle": None,
            }

    def invoke(self, *, session_id: str, prompt: str, attempt_id: str) -> dict[str, Any]:
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": False, "error": "unknown_session"}
            if binding.closed:
                return {"ok": False, "error": "session_closed"}
            if binding.attempt_id != attempt_id:
                return {"ok": False, "error": "cross_attempt_session"}
            if self._remaining <= 0:
                return {"ok": False, "error": "agent_invocation_limit"}
            # Reserve before spawn (no refund on failure).
            self._remaining -= 1
            kind = binding.executor_kind
            model = binding.model

        try:
            executor = self.resolve_executor(kind, model=model)
        except KeyError:
            return {"ok": False, "error": "executor_unknown", "executor": kind}

        result = executor.invoke(prompt)
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
        }

    def close_session(self, *, session_id: str) -> dict[str, Any]:
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": True, "already": "missing"}
            binding.closed = True
            return {"ok": True}


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
            try:
                self._server.close()
            except OSError:
                pass
        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass

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
                try:
                    _send_msg(conn, {"ok": False, "error": type(exc).__name__, "message": str(exc)})
                except Exception:  # noqa: BLE001
                    pass

    def _handle(self, req: dict[str, Any]) -> dict[str, Any]:
        op = req.get("op")
        if op == "open":
            return self.service.open_session(
                attempt_id=str(req.get("attempt_id") or ""),
                profile_id=str(req.get("profile_id") or ""),
            )
        if op == "invoke":
            return self.service.invoke(
                session_id=str(req.get("session_id") or ""),
                prompt=str(req.get("prompt") or ""),
                attempt_id=str(req.get("attempt_id") or ""),
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
