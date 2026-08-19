"""CLI: ``bora agent install|list|show|uninstall`` (design/14).

Install writes only the local cache ($BORA_HOME/agents) — never profiles /
task.yaml. Run with ``bora run <dataset> --agent <id>@<version>``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

agent_app = typer.Typer(
    name="agent",
    help=(
        "Manage local Agent definitions (bora.agent/1).\n\n"
        "install writes only ~/.bora/agents (or $BORA_HOME/agents) — it does "
        "NOT modify profiles.yaml / task.yaml. Bind at run time with "
        "`bora run <dataset> --agent <id>@<version>` or `--agent <role>=<ref>`."
    ),
    no_args_is_help=True,
)


def register(app: typer.Typer) -> None:
    app.add_typer(agent_app, name="agent")


AGENT_OPTION_HELP = (
    "Bind an installed Agent (bora.agent/1) for this run; repeatable. "
    "Forms: <id>@<version> (all roles), <role>=<ref> (one role), or a local "
    "path to an agent dir / agent.yaml. Mutually exclusive with --profiles."
)


def resolve_agent_option(agent: list[str] | None, profiles: Path | None) -> Path | None:
    """Shared --agent handling: mutual exclusion + projection into a profiles file."""
    if not agent:
        return profiles
    if profiles is not None:
        typer.echo(
            "invalid_override: --agent and --profiles are mutually exclusive",
            err=True,
        )
        raise typer.Exit(code=2)
    from bora.application.composition import build_agent_projection
    from bora.config.errors import ConfigError

    try:
        return build_agent_projection()(list(agent))
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@agent_app.command("install")
def agent_install(
    source: Annotated[
        str,
        typer.Argument(
            help=(
                "Local path to a bora.agent/1 directory, or registry locator "
                "org/agent_id@version | org/agent_id@sha256:… (remote requires credentials)"
            )
        ),
    ],
) -> None:
    """Install an agent into the local cache (never edits profiles)."""
    from bora.config.errors import ConfigError

    src_path = Path(source)
    if "@" in source and not src_path.exists():
        from bora.application.composition import build_agent_commands

        cmds = build_agent_commands()
        try:
            summary = cmds.install_agent_from_registry(source)
        except ConfigError as exc:
            typer.echo(
                json.dumps({"ok": False, "error": exc.error_code, "message": str(exc)}),
                err=True,
            )
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, sort_keys=True))
        return

    from bora.agents.store import install_from_path

    try:
        entry = install_from_path(src_path)
    except ConfigError as exc:
        typer.echo(
            json.dumps({"ok": False, "error": exc.error_code, "message": str(exc)}),
            err=True,
        )
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(json.dumps({"ok": False, "error": "io_error", "message": str(exc)}), err=True)
        raise typer.Exit(code=2) from exc
    payload = entry.as_dict()
    payload["ok"] = True
    payload["ref"] = f"{entry.agent_id}@{entry.version}"
    typer.echo(json.dumps(payload, sort_keys=True))


@agent_app.command("publish")
def agent_publish(
    source: Annotated[Path, typer.Argument(help="Local bora.agent/1 package directory")],
    org: Annotated[str, typer.Option("--org", help="Organization id (required)")],
    public: Annotated[bool, typer.Option("--public", help="Publish as public")] = False,
) -> None:
    """Publish an agent package to the Registry (package_kind=agent)."""
    from bora.application.composition import build_agent_commands
    from bora.config.errors import ConfigError

    try:
        summary = build_agent_commands().publish_agent(source, public=public, org=org)
    except ConfigError as exc:
        typer.echo(
            json.dumps({"ok": False, "error": exc.error_code, "message": str(exc)}),
            err=True,
        )
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, sort_keys=True))


@agent_app.command("list")
def agent_list() -> None:
    """List installed agents from the local index."""
    from bora.agents.store import list_installed

    rows = [e.as_dict() for e in list_installed()]
    typer.echo(json.dumps({"agents": rows, "ok": True}, sort_keys=True))


@agent_app.command("show")
def agent_show(
    ref: Annotated[str, typer.Argument(help="Installed id (<id> or <id>@<version>)")],
) -> None:
    """Show one installed agent's manifest (secret-free by construction)."""
    from bora.agents.manifest import load_agent_manifest
    from bora.agents.store import load_index, resolve_installed_ref, resolve_package_root
    from bora.config.errors import ConfigError

    try:
        agent_id, _, version = ref.rpartition("@")
        if agent_id and version:
            entry, root = resolve_installed_ref(agent_id, version)
        else:
            entry = load_index().find(ref)
            if entry is None:
                raise ConfigError("invalid_package", f"agent not installed: {ref!r}", location=ref)
            root = resolve_package_root(entry)
        manifest = load_agent_manifest(root)
    except ConfigError as exc:
        typer.echo(
            json.dumps({"ok": False, "error": exc.error_code, "message": str(exc)}),
            err=True,
        )
        raise typer.Exit(code=2) from exc
    payload = manifest.as_dict()
    payload["ok"] = True
    payload["agent_id"] = entry.agent_id
    payload["digest"] = entry.digest
    typer.echo(json.dumps(payload, sort_keys=True))


@agent_app.command("uninstall")
def agent_uninstall(
    agent_id: Annotated[str, typer.Argument(help="Installed id to remove from cache")],
) -> None:
    """Remove an agent from cache/index. Does not edit profiles."""
    from bora.agents.store import uninstall

    if not uninstall(agent_id):
        typer.echo(
            json.dumps({"agent_id": agent_id, "error": "agent_not_installed", "ok": False}),
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(json.dumps({"ok": True, "uninstalled": agent_id}, sort_keys=True))
