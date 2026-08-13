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
        org: Annotated[
            str,
            typer.Option(
                "--org",
                help="Organization id that owns this package (required).",
            ),
        ],
        public: Annotated[
            bool,
            typer.Option(
                "--public",
                help="Create a public release (default: private).",
            ),
        ] = False,
        replace: Annotated[
            bool,
            typer.Option(
                "--replace",
                help="Overwrite same database_id@version if org owner (default: conflict 409).",
            ),
        ] = False,
        draft: Annotated[
            bool,
            typer.Option(
                "--draft",
                help="Upload/overwrite the dataset draft slot instead of creating a release.",
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
        """Publish a local Database package to the configured Registry (must attach --org)."""
        from bora.application.composition import build_publish_command

        publish_database = build_publish_command().publish_database
        from bora.config.errors import ConfigError

        try:
            summary = publish_database(
                database,
                public=public,
                org=org,
                replace=replace,
                draft=draft,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"invalid_package: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @app.command("release")
    def release_command(
        database_id: Annotated[
            str,
            typer.Argument(help="Dataset id whose current draft becomes a durable release."),
        ],
        public: Annotated[
            bool,
            typer.Option(
                "--public",
                help="Publish the release as public (default: draft visibility).",
            ),
        ] = False,
        replace: Annotated[
            bool,
            typer.Option(
                "--replace",
                help="Overwrite same database_id@version if org owner (default: conflict 409).",
            ),
        ] = False,
        version: Annotated[
            str | None,
            typer.Option(
                "--version",
                help="Override version (default: bora.yaml inside the draft).",
            ),
        ] = None,
        registry_url: Annotated[
            str | None,
            typer.Option(
                "--registry-url",
                help="Override BORA_REGISTRY_URL / credentials file registry URL.",
            ),
        ] = None,
    ) -> None:
        """Owner: promote the current dataset draft to an immutable release."""
        from bora.application.composition import build_publish_command
        from bora.config.errors import ConfigError

        release_draft = build_publish_command().release_draft
        try:
            summary = release_draft(
                database_id,
                public=public,
                replace=replace,
                version=version,
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
        from bora.application.composition import build_login_command

        login_registry = build_login_command().login_registry
        from bora.config.errors import ConfigError

        try:
            summary = login_registry(registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
