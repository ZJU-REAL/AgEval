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
        from bora.application.composition import build_registry_org_commands

        create_org = build_registry_org_commands().create_org
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
        from bora.application.composition import build_registry_org_commands

        list_orgs = build_registry_org_commands().list_orgs
        from bora.config.errors import ConfigError

        try:
            summary = list_orgs(registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("org-add-member")
    def registry_org_add_member(
        org_id: Annotated[str, typer.Argument(help="Org slug.")],
        user: Annotated[str, typer.Argument(help="GitHub login to add.")],
        role: Annotated[
            str,
            typer.Option("--role", help="owner or member."),
        ] = "member",
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Add a member by GitHub login. Target need not be logged in."""
        from bora.application.composition import build_registry_org_commands

        add_member = build_registry_org_commands().add_member
        from bora.config.errors import ConfigError

        try:
            summary = add_member(
                org_id=org_id,
                user_id=user,
                role=role,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("org-remove-member")
    def registry_org_remove_member(
        org_id: Annotated[str, typer.Argument(help="Org slug.")],
        user: Annotated[str, typer.Argument(help="GitHub login to remove.")],
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Remove a member by GitHub login. Target need not be logged in."""
        from bora.application.composition import build_registry_org_commands

        remove_member = build_registry_org_commands().remove_member
        from bora.config.errors import ConfigError

        try:
            summary = remove_member(
                org_id=org_id,
                user_id=user,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("org-set-role")
    def registry_org_set_role(
        org_id: Annotated[str, typer.Argument(help="Org slug.")],
        user: Annotated[str, typer.Argument(help="GitHub login to update.")],
        role: Annotated[
            str,
            typer.Option("--role", help="owner or member."),
        ],
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Change an existing member's role. Target must already belong to the org."""
        from bora.application.composition import build_registry_org_commands

        set_member_role = build_registry_org_commands().set_member_role
        from bora.config.errors import ConfigError

        try:
            summary = set_member_role(
                org_id=org_id,
                user_id=user,
                role=role,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("org-transfer")
    def registry_org_transfer(
        org_id: Annotated[str, typer.Argument(help="Org slug.")],
        user: Annotated[str, typer.Argument(help="Existing member who becomes owner.")],
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Hand ownership to an existing member; caller becomes member."""
        from bora.application.composition import build_registry_org_commands

        transfer = build_registry_org_commands().transfer
        from bora.config.errors import ConfigError

        try:
            summary = transfer(
                org_id=org_id,
                user_id=user,
                registry_url=registry_url,
            )
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
        from bora.application.composition import build_registry_list_commands

        list_packages = build_registry_list_commands().list_packages
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
        from bora.application.composition import build_registry_list_commands

        show_package = build_registry_list_commands().show_package
        from bora.config.errors import ConfigError

        try:
            summary = show_package(ref, registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("delete")
    def registry_delete_command(
        ref: Annotated[
            str,
            typer.Argument(help="Package release: database_id@version"),
        ],
        yes: Annotated[
            bool,
            typer.Option("--yes", help="Confirm destructive delete (required)."),
        ] = False,
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Delete a package release. Org owner (or admin) only; requires --yes."""
        from bora.application.composition import build_registry_list_commands

        delete_package_release = build_registry_list_commands().delete_package_release
        from bora.config.errors import ConfigError

        if not yes:
            typer.echo("refusing to delete without --yes", err=True)
            raise typer.Exit(code=2)
        try:
            summary = delete_package_release(ref, registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("set-visibility")
    def registry_set_visibility_command(
        ref: Annotated[
            str,
            typer.Argument(help="Package release: database_id@version"),
        ],
        visibility: Annotated[
            str,
            typer.Option("--visibility", help="public | private"),
        ],
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry URL."),
        ] = None,
    ) -> None:
        """Set package release visibility after publish. Org owner (or admin) only."""
        from bora.application.composition import build_registry_list_commands

        set_package_visibility = build_registry_list_commands().set_package_visibility
        from bora.config.errors import ConfigError

        if visibility not in {"public", "private"}:
            typer.echo("visibility must be public or private", err=True)
            raise typer.Exit(code=2)
        try:
            summary = set_package_visibility(ref, visibility=visibility, registry_url=registry_url)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    app.add_typer(sub, name="registry")
