"""CLI executors, publish, and login commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Attach commands to the root Typer app."""

    @app.command("executors")
    def executors_command(
        verbose: Annotated[
            bool,
            typer.Option(
                "--verbose",
                "-v",
                help="Include capability detail (tools/session + default credential env names).",
            ),
        ] = False,
    ) -> None:
        """List supported agent executor kinds and whether host binaries are on PATH.

        Thin CLI: inventory logic lives in ``bora.adapters.executor_inventory``.
        """
        from bora.adapters.executor_inventory import build_executor_inventory

        summary = build_executor_inventory(verbose=verbose)
        typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    @app.command("publish")
    def publish_command(
        database: Annotated[
            Path,
            typer.Argument(help="Local Database root to publish (bora.database/1)."),
        ],
        public: Annotated[
            bool,
            typer.Option(
                "--public",
                help="Create a public release (default: private).",
            ),
        ] = False,
        registry_url: Annotated[
            str | None,
            typer.Option(
                "--registry-url",
                help="Override BORA_REGISTRY_URL / credentials file registry URL.",
            ),
        ] = None,
    ) -> None:
        """Publish a local Database package to the configured Registry (Spec 21)."""
        from bora.application.publish_command import publish_database
        from bora.config.errors import ConfigError

        try:
            summary = publish_database(
                database,
                public=public,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"invalid_package: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @app.command("login")
    def login_command(
        registry_url: Annotated[
            str | None,
            typer.Option(
                "--registry-url",
                help="Override BORA_REGISTRY_URL / credentials file registry URL.",
            ),
        ] = None,
    ) -> None:
        """GitHub Device Flow login; write ``~/.bora/credentials`` (mode 0600)."""
        from bora.application.login_command import login_registry
        from bora.config.errors import ConfigError

        try:
            summary = login_registry(registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
