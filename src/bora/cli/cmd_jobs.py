"""CLI local Jobs commands (delete on-disk evidence; no Registry)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Create and mount the ``jobs`` sub-app."""

    sub = typer.Typer(
        name="jobs",
        help="Local Jobs under a Database root (no Registry).",
        no_args_is_help=True,
        add_completion=False,
    )

    @sub.command("delete")
    def jobs_delete_command(
        local: Annotated[
            Path,
            typer.Option("--local", help="Local Database root (bora.database/1)."),
        ],
        job: Annotated[
            str,
            typer.Option("--job", help="Job id: suite_run_id or unclaimed single run_id."),
        ],
        yes: Annotated[
            bool,
            typer.Option("--yes", help="Confirm destructive delete (required)."),
        ] = False,
    ) -> None:
        """Delete a local Job tree. Suite delete always cascades Attempts."""
        from bora.application.composition import build_local_jobs_commands
        from bora.config.errors import ConfigError

        cmds = build_local_jobs_commands()
        try:
            if not yes:
                preview = cmds.preview_delete_job(local, job_id=job)
                typer.echo(
                    json.dumps(preview, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                )
                typer.echo("refusing to delete without --yes", err=True)
                raise typer.Exit(code=2)
            summary = cmds.delete_job(local, job_id=job, yes=True)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    app.add_typer(sub, name="jobs")
