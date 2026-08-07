"""CLI view, tasks, and lock commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from bora.application.composition import build_lock_command
from bora.config.errors import ConfigError


def register(app: typer.Typer) -> None:
    """Attach commands to the root Typer app."""

    @app.command("view")
    def view_command(
        database: Annotated[
            Path,
            typer.Argument(help="Local Database root to open (bora.database/1)."),
        ],
        host: Annotated[
            str,
            typer.Option("--host", help="Bind host (default loopback only)."),
        ] = "127.0.0.1",
        port: Annotated[
            int,
            typer.Option("--port", help="HTTP port (0 = ephemeral)."),
        ] = 8765,
        no_browser: Annotated[
            bool,
            typer.Option("--no-browser", help="Do not open a browser tab."),
        ] = False,
    ) -> None:
        """Start local Jobs→Tasks→Trial results UI for a Database (no Registry)."""
        from bora.config.errors import ConfigError
        from bora.viewer.server import serve_viewer

        try:
            serve_viewer(
                database,
                host=host,
                port=port,
                open_browser=not no_browser,
                block=True,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except FileNotFoundError as exc:
            typer.echo(f"viewer: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            # Prefer strerror / args message (serve_viewer embeds host:port on bind fail).
            detail = exc.strerror or (exc.args[1] if len(exc.args) > 1 else None) or str(exc)
            typer.echo(f"viewer: {detail}", err=True)
            raise typer.Exit(code=2) from exc

    @app.command("tasks")
    def tasks_command(
        database: Annotated[
            Path,
            typer.Argument(help="Path to the Database root directory (bora.database/1)."),
        ],
    ) -> None:
        """List member task ids under a Database (fail closed on empty or id mismatch)."""
        from bora.config.database import list_tasks, load_database_manifest
        from bora.config.errors import ConfigError

        try:
            manifest = load_database_manifest(database)
            ids = list_tasks(database, manifest=manifest)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"invalid_package: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        payload = {
            "database_id": manifest.database_id,
            "version": manifest.version,
            "tasks": ids,
            "count": len(ids),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @app.command("lock")
    def lock_command(
        package: Annotated[
            str,
            typer.Argument(
                help=(
                    "Database root path or registry ref "
                    "(<database_id>@<version> | <database_id>@sha256:<digest>)."
                ),
            ),
        ],
        task: Annotated[
            str | None,
            typer.Option(
                "--task",
                help="Member task id (required). Must match tasks/<id>/task.yaml task_id.",
            ),
        ] = None,
        set_overrides: Annotated[
            list[str] | None,
            typer.Option(
                "--set",
                help=(
                    "Repeatable override as <JSON Pointer>=<JSON value>, e.g. "
                    "`/parameters/seed=7`. Only allowlisted pointers are accepted."
                ),
            ),
        ] = None,
    ) -> None:
        """Resolve a Database member, lock its task.yaml; print a deterministic JSON summary."""
        if task is None or not str(task).strip():
            typer.echo(
                "invalid_override: --task is required "
                "(suite-wide lock without --task is not supported)",
                err=True,
            )
            raise typer.Exit(code=2)

        use_case = build_lock_command()
        try:
            summary = use_case.run(
                database_root=package,
                task_id=task,
                set_overrides=set_overrides or (),
            )
        except ConfigError as exc:
            # Stable operator-facing failure: exit 2, message on stderr, empty stdout.
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"invalid_package: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        # Success: exactly one JSON object on stdout (stable key order via model).
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
