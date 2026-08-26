"""CLI cache list/path/purge commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ageval.cli.present import emit


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
        """List verified entries under AGEVAL_CACHE_ROOT / .ageval/cache."""
        from ageval.application.composition import build_registry_list_commands

        cache_list = build_registry_list_commands().cache_list

        summary = cache_list()
        emit(summary)

    @sub.command("path")
    def cache_path_command(
        ref: Annotated[
            str,
            typer.Argument(help="Package ref already present in the local cache."),
        ],
    ) -> None:
        """Print filesystem path of a verified cache entry."""
        from ageval.application.composition import build_registry_list_commands

        cache_path = build_registry_list_commands().cache_path
        from ageval.config.errors import ConfigError

        try:
            summary = cache_path(ref)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        emit(summary)

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
        from ageval.application.composition import build_registry_list_commands

        cache_purge = build_registry_list_commands().cache_purge
        from ageval.config.errors import ConfigError

        try:
            summary = cache_purge(target, yes=yes)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        emit(summary)

    app.add_typer(sub, name="cache")
