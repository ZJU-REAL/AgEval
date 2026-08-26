"""CLI cancel command (upload goes through ``ageval results upload``)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ageval.cli.present import emit


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
            typer.Option("--store", help="ControlStore sqlite path (default .ageval/control.db)."),
        ] = None,
        dataset: Annotated[
            Path | None,
            typer.Option(
                "--dataset",
                help=(
                    "Dataset root for suite cancel when ControlStore has no record "
                    "(writes suite-runs/<id>/cancel.requested)."
                ),
            ),
        ] = None,
    ) -> None:
        """Cancel a durable Run or suite job.

        Suite: writes ``cancel.requested`` so no new units start; SIGTERM stored
        pid when present. Single Run: ControlStore cancel.
        """
        import os
        import signal

        from ageval.application.composition import build_suite_runner

        _suite = build_suite_runner()
        is_suite_run_locator = _suite.is_suite_run_locator
        request_suite_cancel = _suite.request_suite_cancel
        from ageval.control.store import ControlStore

        path = store or (Path.cwd() / ".ageval" / "control.db")
        cs = ControlStore(path)
        rec = cs.get(run_id)
        payload: dict = dict((rec or {}).get("payload") or {})
        kind = str(payload.get("kind") or "")
        db_root = dataset
        if db_root is None and payload.get("dataset_root"):
            db_root = Path(str(payload["dataset_root"]))
        is_suite = is_suite_run_locator(run_id, dataset_root=db_root, control_kind=kind)

        cancel_file = None
        if is_suite and db_root is not None:
            cancel_file = str(request_suite_cancel(db_root, run_id))

        if rec is None and not is_suite:
            emit({"ok": False, "error": "unknown_run", "run_id": run_id})
            raise typer.Exit(code=2)
        if rec is None and is_suite and cancel_file is None:
            emit(
                {
                    "ok": False,
                    "error": "unknown_suite",
                    "run_id": run_id,
                    "hint": "pass --dataset <root> or cancel while suite is registered",
                }
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
        emit(
            {
                "ok": True,
                "run_id": run_id,
                "status": "cancelled",
                "kind": "suite" if is_suite else "run",
                "version": version,
                "sigterm_sent": killed,
                "cancel_file": cancel_file,
            }
        )
