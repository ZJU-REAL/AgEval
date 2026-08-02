"""Public CLI entrypoint (``bora`` console script).

This module maps argv → use case → stdout/stderr/exit code. It must not
implement Config merge, path validation, or digests itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from bora.application.composition import build_lock_command
from bora.config.errors import ConfigError

# Typer application object exposed as the console script target.
app = typer.Typer(
    name="bora",
    help=(
        "BORA — Bounded Orchestration for Runtime Agents.\n\n"
        "v0.1 public surface is Config-only: `bora lock` produces a deterministic, "
        "secret-free lock summary. This is a Core engineering checkpoint, not "
        "runnable-mvp evidence."
    ),
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """Root callback (no global options in v0.1)."""


@app.command("lock")
def lock_command(
    package: Annotated[
        Path,
        typer.Argument(help="Path to the Task Package root directory."),
    ],
    task: Annotated[
        str,
        typer.Option("--task", help="Task id that must match bora.yaml task_id."),
    ],
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
    """Load, validate, and lock a Task Package; print a deterministic JSON summary."""
    use_case = build_lock_command()
    try:
        summary = use_case.run(
            package_root=package,
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


def main() -> None:
    """Programmatic entry used by tests that invoke the module directly."""
    app(prog_name="bora")


if __name__ == "__main__":
    main()
    sys.exit(0)
