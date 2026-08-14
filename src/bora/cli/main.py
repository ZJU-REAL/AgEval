"""Public CLI entrypoint (``bora`` console script).

This module maps argv → use case → stdout/stderr/exit code. It must not
implement Config merge, path validation, or digests itself.

Command implementations live in ``cmd_*`` modules (chore #31).
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from bora.cli import (
    cmd_cache,
    cmd_campaign_run,
    cmd_cancel_submit,
    cmd_evidence_status,
    cmd_executors_publish_login,
    cmd_jobs,
    cmd_plugin,
    cmd_registry,
    cmd_results,
    cmd_view_tasks_lock,
)
from bora.cli.version import version_callback

# Typer application object exposed as the console script target.
app = typer.Typer(
    name="bora",
    help=(
        "BORA — Bounded Orchestration for Runtime Agents.\n\n"
        "CLI path arguments are Database roots (`bora.database/1`). "
        "Use `--task <id>` to select a member under `tasks/<id>/task.yaml`. "
        "List members with `bora tasks <database>`."
    ),
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show package version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Global options (``-h`` / ``--help``, ``-V`` / ``--version``)."""
    del version  # handled by eager callback


cmd_campaign_run.register(app)
cmd_evidence_status.register(app)
cmd_cancel_submit.register(app)
cmd_executors_publish_login.register(app)
cmd_plugin.register(app)
cmd_registry.register(app)
cmd_cache.register(app)
cmd_results.register(app)
cmd_jobs.register(app)
cmd_view_tasks_lock.register(app)


def main() -> None:
    """Programmatic entry used by tests that invoke the module directly."""
    app(prog_name="bora")


if __name__ == "__main__":
    main()
    sys.exit(0)
