"""CLI registry list/show commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Create and mount the ``registry`` sub-app."""

    sub = typer.Typer(
        name="registry",
        help="List/show packages and orgs on the configured Registry.",
        no_args_is_help=True,
        add_completion=False,
    )

    @sub.command("org-create")
    def registry_org_create(
        name: Annotated[str, typer.Argument(help="Org slug (lowercase).")],
        display_name: Annotated[
            str | None,
            typer.Option("--display-name", help="Optional display name."),
        ] = None,
        claimable: Annotated[
            bool,
            typer.Option("--claimable", help="Allow later claim as owner."),
        ] = False,
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Create an organization; caller becomes owner."""
        from bora.application.registry_org_command import create_org
        from bora.config.errors import ConfigError

        try:
            summary = create_org(
                name=name,
                display_name=display_name,
                is_claimable=claimable,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("org-list")
    def registry_org_list(
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """List organizations the current user belongs to."""
        from bora.application.registry_org_command import list_orgs
        from bora.config.errors import ConfigError

        try:
            summary = list_orgs(registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("list")
    def registry_list_command(
        prefix: Annotated[
            str | None,
            typer.Option("--prefix", help="Filter by database_id prefix."),
        ] = None,
        visibility: Annotated[
            str | None,
            typer.Option("--visibility", help="public | private (requires scope for private)."),
        ] = None,
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """List package releases visible to the current credentials."""
        from bora.application.registry_list_command import list_packages
        from bora.config.errors import ConfigError

        try:
            summary = list_packages(
                database_id_prefix=prefix,
                visibility=visibility,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("show")
    def registry_show_command(
        ref: Annotated[
            str,
            typer.Argument(help="Package ref: database_id@version or @sha256:…"),
        ],
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Show release metadata (digest, size, visibility)."""
        from bora.application.registry_list_command import show_package
        from bora.config.errors import ConfigError

        try:
            summary = show_package(ref, registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    app.add_typer(sub, name="registry")
