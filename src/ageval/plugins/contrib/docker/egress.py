"""Parent-side HTTP(S) proxy: only bound LLM hosts, then stop.

Used when job ``environment_options.egress: llm``. The agent box gets
``HTTPS_PROXY``; ACP stdio does not go through this proxy.
"""

from __future__ import annotations

import contextlib
import select
import socket
import threading
from collections.abc import Sequence
from urllib.parse import urlsplit


class AllowlistProxy:
    """A CONNECT/HTTP proxy that forwards only allowlisted hostnames."""

    def __init__(self, allowlist: Sequence[str]) -> None:
        self._allow = frozenset(_hostname(item) for item in allowlist if _hostname(item))
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self.port = 0

    def start(self) -> int:
        if not self._allow:
            raise RuntimeError("egress: llm requires at least one bound base_url host")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 0))
        sock.listen(64)
        sock.settimeout(0.5)
        self._sock = sock
        self.port = int(sock.getsockname()[1])
        self._thread = threading.Thread(target=self._loop, name="ageval-egress", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._closed.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.close()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    def allowed(self, host: str) -> bool:
        return _hostname(host) in self._allow

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._closed.is_set():
            try:
                conn, _addr = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        remote: socket.socket | None = None
        try:
            conn.settimeout(30.0)
            head = _read_headers(conn)
            if not head:
                return
            first, _, _rest = head.partition(b"\r\n")
            line = first.decode("ascii", errors="replace")
            parts = line.split()
            if len(parts) < 2:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                return
            method, target = parts[0].upper(), parts[1]
            host, port = _target_host_port(method, target, head)
            if host is None or not self.allowed(host):
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                return
            remote = socket.create_connection((host, port), timeout=30.0)
            if method == "CONNECT":
                conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _tunnel(conn, remote)
                return
            remote.sendall(head)
            _tunnel(conn, remote)
        except OSError:
            return
        finally:
            with contextlib.suppress(OSError):
                conn.close()
            if remote is not None:
                with contextlib.suppress(OSError):
                    remote.close()


def _hostname(raw: str) -> str:
    text = str(raw or "").strip().lower().rstrip(".")
    if not text:
        return ""
    if "://" in text:
        text = urlsplit(text).hostname or ""
    if ":" in text and not text.startswith("["):
        text = text.rsplit(":", 1)[0]
    return text.strip("[]")


def _target_host_port(method: str, target: str, head: bytes) -> tuple[str | None, int]:
    if method == "CONNECT":
        host, sep, port_s = target.rpartition(":")
        if not sep:
            return _hostname(target) or None, 443
        try:
            return _hostname(host) or None, int(port_s)
        except ValueError:
            return None, 0
    if target.startswith("http://") or target.startswith("https://"):
        parsed = urlsplit(target)
        host = parsed.hostname
        default = 443 if parsed.scheme == "https" else 80
        return host, parsed.port or default
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(b"host:"):
            value = line.split(b":", 1)[1].decode("ascii", errors="replace").strip()
            host, sep, port_s = value.rpartition(":")
            if sep and port_s.isdigit():
                return _hostname(host) or None, int(port_s)
            return _hostname(value) or None, 80
    return None, 0


def _read_headers(conn: socket.socket) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < 65536:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def _tunnel(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    while sockets:
        readable, _, _errored = select.select(sockets, [], sockets, 30.0)
        if not readable:
            return
        for sock in readable:
            other = right if sock is left else left
            data = sock.recv(65536)
            if not data:
                return
            other.sendall(data)
