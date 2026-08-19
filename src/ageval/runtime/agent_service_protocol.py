"""Unix-socket framing and server for ParentAgentService.

Worker/SDK talks length-prefixed JSON over a Unix domain socket.
"""

from __future__ import annotations

import contextlib
import json
import socket
import struct
import threading
from pathlib import Path
from typing import Any

from ageval.runtime.parent_agent_service import ParentAgentService


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
        self._thread = threading.Thread(target=self._loop, name="ageval-agent-service", daemon=True)
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
            actor_raw = req.get("actor_id")
            actor_id = (
                str(actor_raw).strip() if isinstance(actor_raw, str) and actor_raw.strip() else None
            )
            return self.service.open_session(
                profile_id=str(req.get("profile_id") or ""),
                actor_id=actor_id,
            )
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
    from ageval.runtime.offline import is_offline_agent

    if is_offline_agent() and payload.get("op") == "invoke":
        return {"ok": False, "error": "offline_forced", "structured": None}
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(sock_path)
        _send_msg(conn, payload)
        return _recv_msg(conn)
    finally:
        conn.close()
