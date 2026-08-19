"""Task worker entrypoint: load package harness in a child process.

Parent never imports package modules. Communication uses a simple length-prefixed
JSON protocol over a connected stream (socketpair endpoint inherited as FD).

Usage (child)::

    python -m ageval.runtime.task_worker --fd <n>
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import struct
import sys
import traceback
from pathlib import Path
from typing import Any


def _recv_msg(fd: int) -> dict[str, Any]:
    hdr = os.read(fd, 4)
    if len(hdr) < 4:
        raise EOFError("short header")
    (n,) = struct.unpack("!I", hdr)
    data = b""
    while len(data) < n:
        chunk = os.read(fd, n - len(data))
        if not chunk:
            raise EOFError("short body")
        data += chunk
    return json.loads(data.decode("utf-8"))


def _send_msg(fd: int, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    os.write(fd, struct.pack("!I", len(raw)) + raw)


def _inject_import_paths(package_root: Path, database_root: Path | None) -> None:
    """Make task root and Dataset root importable (#68).

    Authoritative prefix: ``[task_dir, database_root, ...]``.
    Do **not** inject ``shared/lib`` or ``tasks/<id>/lib`` as path roots —
    authors import ``shared.lib.*`` / ``lib.*``.
    """
    # Insert database_root first, then task_dir so task_dir ends up at front.
    if database_root is not None:
        db = str(database_root.resolve())
        if db not in sys.path:
            sys.path.insert(0, db)
    task = str(package_root.resolve())
    if task in sys.path:
        sys.path.remove(task)
    sys.path.insert(0, task)


def _load_entrypoint(
    package_root: Path, entrypoint: str, *, database_root: Path | None = None
) -> Any:
    module_name, _, func_name = entrypoint.partition(":")
    if not module_name or not func_name:
        raise ValueError(f"invalid entrypoint: {entrypoint}")
    # Only harness.py at package root for v0.5.
    path = package_root / "harness.py"
    if not path.is_file():
        raise FileNotFoundError("harness.py missing")
    spec = importlib.util.spec_from_file_location("ageval_task_harness", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load harness.py")
    mod = importlib.util.module_from_spec(spec)
    _inject_import_paths(package_root, database_root)
    spec.loader.exec_module(mod)
    fn = getattr(mod, func_name)
    return fn


async def _run(fd: int) -> int:
    launch = _recv_msg(fd)
    package_root = Path(launch["package_root"])
    entrypoint = launch["entrypoint"]
    params = launch.get("params") or {}
    attempt_id = launch["attempt_id"]
    artifact_dir = Path(launch["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    # Optional Attempt workspace (L1 host bind); default package root for L0.
    ws_raw = launch.get("workspace_root")
    workspace_root = Path(ws_raw) if ws_raw else package_root
    # #68 Dataset root for shared.lib.* import + code-path assets.
    db_raw = launch.get("database_root")
    database_root = Path(db_raw) if db_raw else None

    # Build SDK context inside worker only.
    from ageval_sdk.context import HarnessContext, HarnessParameterView, RunScope
    from ageval_sdk.terminal import HarnessTerminal

    ctx = HarnessContext(
        params=HarnessParameterView(params),
        scope=RunScope(
            attempt_id=attempt_id,
            trial_id=launch.get("trial_id", ""),
            run_id=launch.get("run_id", ""),
        ),
        workspace_root=workspace_root,
        artifact_dir=artifact_dir,
        database_root=database_root,
    )
    try:
        fn = _load_entrypoint(package_root, entrypoint, database_root=database_root)
        result = fn(ctx)
        if asyncio.iscoroutine(result):
            result = await result
        if isinstance(result, HarnessTerminal):
            terminal = result.to_dict()
        elif result is None:
            terminal = HarnessTerminal.completed().to_dict()
        else:
            terminal = HarnessTerminal.failed("invalid_terminal").to_dict()
        published = {k: str(v) for k, v in (ctx._published or {}).items()}
        _send_msg(
            fd,
            {
                "ok": True,
                "terminal": terminal,
                "published": published,
                "attempt_id": attempt_id,
            },
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        _send_msg(
            fd,
            {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "attempt_id": attempt_id,
                "traceback": traceback.format_exc(limit=5),
            },
        )
        return 1
    finally:
        ctx.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ageval.runtime.task_worker")
    parser.add_argument("--fd", type=int, required=True)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.fd))


if __name__ == "__main__":
    raise SystemExit(main())
