"""CLI cache list/path/purge commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Create and mount the ``cache`` sub-app."""

    sub = typer.Typer(
        name="cache",
        help="Inspect / purge local verified package cache.",
        no_args_is_help=True,
        add_completion=False,
    )

    @sub.command("list")
    def cache_list_command() -> None:
        """List verified entries under BORA_CACHE_ROOT / .bora/cache."""
        from bora.application.registry_list_command import cache_list

        summary = cache_list()
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("path")
    def cache_path_command(
        ref: Annotated[
            str,
            typer.Argument(help="Package ref already present in the local cache."),
        ],
    ) -> None:
        """Print filesystem path of a verified cache entry."""
        from bora.application.registry_list_command import cache_path
        from bora.config.errors import ConfigError

        try:
            summary = cache_path(ref)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("purge")
    def cache_purge_command(
        target: Annotated[
            str | None,
            typer.Argument(help="Ref to purge, or 'all'. Default: all."),
        ] = None,
        yes: Annotated[
            bool,
            typer.Option("--yes", help="Confirm destructive purge."),
        ] = False,
    ) -> None:
        """Delete verified cache entries (requires --yes)."""
        from bora.application.registry_list_command import cache_purge
        from bora.config.errors import ConfigError

        try:
            summary = cache_purge(target, yes=yes)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    app.add_typer(sub, name="cache")
