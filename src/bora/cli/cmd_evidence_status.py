"""CLI evidence export and status commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Attach commands to the root Typer app."""

    @app.command("evidence")
    def evidence_export_command(
        evidence_root: Annotated[
            Path,
            typer.Argument(help="Attempt evidence root (Result.logs path)."),
        ],
        out: Annotated[
            Path,
            typer.Option("--out", help="Destination directory for versioned export."),
        ],
    ) -> None:
        """Export sealed trajectory as re-redacted copy (v0.17). Does not change score."""
        from bora.evidence.export import export_trajectory

        result = export_trajectory(evidence_root, out)
        typer.echo(
            json.dumps(
                {
                    "ok": result.ok,
                    "export_path": result.export_path,
                    "invocation_count": result.invocation_count,
                    "error": result.error,
                    "schema": "bora.trajectory.export/1",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise typer.Exit(code=0 if result.ok else 2)

    @app.command("status")
    def status_command(
        run_id: Annotated[str, typer.Argument(help="Run id from ControlStore.")],
        store: Annotated[
            Path | None,
            typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
        ] = None,
    ) -> None:
        """Query durable Run control record (v0.12)."""
        from bora.control.store import ControlStore

        path = store or (Path.cwd() / ".bora" / "control.db")
        rec = ControlStore(path).get(run_id)
        if rec is None:
            typer.echo(json.dumps({"ok": False, "error": "unknown_run", "run_id": run_id}))
            raise typer.Exit(code=2)
        typer.echo(json.dumps({"ok": True, **rec}, sort_keys=True, separators=(",", ":")))
