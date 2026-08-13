"""Best-effort Vite spawn for ``bora view --dev``.

Start ``pnpm --dir apps/viewer dev`` when the monorepo app and pnpm exist.
Otherwise the caller prints the two-process fallback. Never fail the API.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_UI_PORT = 5173
_SPAWN_WAIT_S = 20.0


@dataclass(frozen=True, slots=True)
class DevUiResult:
    started: bool
    reused: bool
    proc: subprocess.Popen[Any] | None
    reason: str


def viewer_app_dir() -> Path | None:
    """Repo ``apps/viewer`` next to this package, when present."""
    # src/bora/viewer/dev_ui.py → parents[3] is the monorepo root.
    candidate = Path(__file__).resolve().parents[3] / "apps" / "viewer"
    if (candidate / "package.json").is_file() and (candidate / "vite.config.ts").is_file():
        return candidate
    return None


def port_listening(host: str, port: int) -> bool:
    """True if *port* accepts TCP on IPv4 or IPv6 (Vite may bind only ::1)."""
    for family, addr in (
        (socket.AF_INET, host),
        (socket.AF_INET6, "::1" if host in {"127.0.0.1", "localhost"} else host),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                target: tuple[Any, ...] = (
                    (addr, port, 0, 0) if family == socket.AF_INET6 else (addr, port)
                )
                if sock.connect_ex(target) == 0:  # type: ignore[arg-type]
                    return True
        except OSError:
            continue
    return False


def vite_command(pnpm: str, *, host: str, port: int) -> list[str]:
    """``pnpm exec vite …`` — do not insert ``--`` (Vite treats it as an arg)."""
    return [
        pnpm,
        "exec",
        "vite",
        "--host",
        host,
        "--port",
        str(port),
        "--strictPort",
    ]


def fallback_commands(*, api_origin: str, ui_port: int) -> tuple[str, str]:
    """Two operator commands when Vite was not started."""
    api = api_origin.rstrip("/")
    return (
        f"VITE_VIEWER_API={api} pnpm --dir apps/viewer dev",
        f"open http://127.0.0.1:{int(ui_port)}/",
    )


def try_start_dev_ui(
    *,
    api_origin: str,
    ui_port: int,
    start: bool,
    wait_s: float = _SPAWN_WAIT_S,
) -> DevUiResult:
    """Spawn or reuse Vite. Never raises for missing toolchain."""
    if not start:
        return DevUiResult(False, False, None, "skipped")
    app = viewer_app_dir()
    if app is None:
        return DevUiResult(False, False, None, "no_app")
    host = "127.0.0.1"
    port = int(ui_port)
    if port_listening(host, port):
        return DevUiResult(True, True, None, "reused")
    pnpm = shutil.which("pnpm")
    if not pnpm:
        return DevUiResult(False, False, None, "no_pnpm")
    if not (app / "node_modules").is_dir():
        return DevUiResult(False, False, None, "no_modules")
    env = os.environ.copy()
    env["VITE_VIEWER_API"] = api_origin.rstrip("/")
    cmd = vite_command(pnpm, host=host, port=port)
    try:
        proc: subprocess.Popen[Any] = subprocess.Popen(
            cmd,
            cwd=str(app),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return DevUiResult(False, False, None, "spawn_failed")
    if _wait_listening(host, port, timeout=wait_s, proc=proc):
        return DevUiResult(True, False, proc, "started")
    stop_dev_ui(proc)
    reason = "exited" if proc.poll() is not None else "timeout"
    return DevUiResult(False, False, None, reason)


def stop_dev_ui(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "posix":
        _kill_posix(proc)
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _wait_listening(
    host: str,
    port: int,
    *,
    timeout: float,
    proc: subprocess.Popen[Any],
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if port_listening(host, port):
            return True
        time.sleep(0.15)
    return False


def _kill_posix(proc: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=1)
