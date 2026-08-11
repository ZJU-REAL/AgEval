"""CLI cancel and submit commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Attach commands to the root Typer app."""

    @app.command("cancel")
    def cancel_command(
        run_id: Annotated[
            str,
            typer.Argument(
                help="Run id or suite_run_id (8-hex suite id or attempt run id).",
            ),
        ],
        store: Annotated[
            Path | None,
            typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
        ] = None,
        database: Annotated[
            Path | None,
            typer.Option(
                "--database",
                help=(
                    "Database root for suite cancel when ControlStore has no record "
                    "(writes suite-runs/<id>/cancel.requested)."
                ),
            ),
        ] = None,
    ) -> None:
        """Cancel a durable Run or suite job (#47 D4).

        Suite: writes ``cancel.requested`` so no new units start; SIGTERM stored
        pid when present. Single Run: same as v0.12 ControlStore cancel.
        """
        import os
        import signal

        from bora.application.suite_run import is_suite_run_locator, request_suite_cancel
        from bora.control.store import ControlStore

        path = store or (Path.cwd() / ".bora" / "control.db")
        cs = ControlStore(path)
        rec = cs.get(run_id)
        payload: dict = dict((rec or {}).get("payload") or {})
        kind = str(payload.get("kind") or "")
        db_root = database
        if db_root is None and payload.get("database_root"):
            db_root = Path(str(payload["database_root"]))
        is_suite = is_suite_run_locator(run_id, database_root=db_root, control_kind=kind)

        cancel_file = None
        if is_suite and db_root is not None:
            cancel_file = str(request_suite_cancel(db_root, run_id))

        if rec is None and not is_suite:
            typer.echo(json.dumps({"ok": False, "error": "unknown_run", "run_id": run_id}))
            raise typer.Exit(code=2)
        if rec is None and is_suite and cancel_file is None:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "unknown_suite",
                        "run_id": run_id,
                        "hint": "pass --database <root> or cancel while suite is registered",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            raise typer.Exit(code=2)

        killed = False
        pid = payload.get("pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except OSError:
                killed = False
        version = None
        if rec is not None or is_suite:
            version = cs.put(
                run_id,
                status="cancelled",
                owner=str((rec or {}).get("owner") or "cli"),
                payload={
                    **payload,
                    "kind": "suite" if is_suite else payload.get("kind") or "run",
                    "cancel_requested": True,
                    "sigterm_sent": killed,
                    "cancel_file": cancel_file,
                },
            )
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "status": "cancelled",
                    "kind": "suite" if is_suite else "run",
                    "version": version,
                    "sigterm_sent": killed,
                    "cancel_file": cancel_file,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @app.command("submit")
    def submit_command(
        package: Annotated[Path, typer.Argument(help="Database root (bora.database/1).")],
        task: Annotated[str, typer.Option("--task", help="Member task id.")],
        store: Annotated[
            Path | None,
            typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
        ] = None,
        wait: Annotated[
            bool,
            typer.Option("--wait", help="Block until Attempt finishes (default: detach child)."),
        ] = False,
    ) -> None:
        """Submit a Run with durable ControlStore record (v0.12).

        Default: spawn a detached child process for ``bora run`` and return run_id.
        ``bora status`` / ``bora cancel`` observe or fence the record (cancel sends SIGTERM
        to stored pid when present).
        """
        import os
        import subprocess
        import uuid

        from bora.control.store import ControlStore

        path = (store or (Path.cwd() / ".bora" / "control.db")).resolve()
        cs = ControlStore(path)
        run_id = f"run_{uuid.uuid4().hex}"
        if wait:
            import asyncio

            from bora.application.composition import build_run_task

            cs.put(
                run_id,
                status="running",
                owner="cli-submit",
                payload={"package": str(package), "task": task, "mode": "wait"},
            )
            try:
                code, result, _details = asyncio.run(build_run_task()(package, task))
                status = "completed" if code == 0 else "failed"
                cs.put(
                    run_id,
                    status=status,
                    owner="cli-submit",
                    payload={
                        "package": str(package),
                        "task": task,
                        "exit_code": code,
                        "result_status": result.status,
                        "evidence_path": result.evidence_path,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                cs.put(
                    run_id,
                    status="failed",
                    owner="cli-submit",
                    payload={"error": f"{type(exc).__name__}: {exc}"},
                )
                typer.echo(json.dumps({"ok": False, "run_id": run_id, "error": str(exc)}))
                raise typer.Exit(code=2) from exc
            typer.echo(
                json.dumps(
                    {
                        "ok": True,
                        "run_id": run_id,
                        "status": status,
                        "exit_code": code,
                        "result_status": result.status,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            raise typer.Exit(code=code)

        # Detached child: re-exec production CLI for the Attempt.
        log_path = path.parent / f"{run_id}.log"
        child_env = os.environ.copy()
        child_env["BORA_CONTROL_RUN_ID"] = run_id
        child_env["BORA_CONTROL_STORE"] = str(path)
        proc = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "bora.cli.main",
                "run",
                str(package.resolve()),
                "--task",
                task,
            ],
            cwd=str(Path.cwd()),
            env=child_env,
            stdout=log_path.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        cs.put(
            run_id,
            status="running",
            owner="cli-submit",
            payload={
                "package": str(package.resolve()),
                "task": task,
                "pid": proc.pid,
                "log_path": str(log_path),
                "mode": "detach",
            },
        )
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "status": "running",
                    "pid": proc.pid,
                    "detached": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
