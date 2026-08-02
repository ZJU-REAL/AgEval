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


@app.command("campaign")
def campaign_command(
    package: Annotated[
        Path,
        typer.Argument(help="Task Package root for campaign matrix."),
    ],
    task: Annotated[
        str,
        typer.Option("--task", help="Base task id."),
    ],
    matrix: Annotated[
        list[str] | None,
        typer.Option(
            "--matrix",
            help="Axis as /parameters/...=[json-array]; only /parameters/* allowed in v0.11.",
        ),
    ] = None,
) -> None:
    """Foreground serial campaign over a parameter matrix (v0.11)."""
    import asyncio

    from bora.application.composition import build_campaign_runner
    from bora.config.errors import ConfigError

    run_campaign = build_campaign_runner()
    try:
        summary = asyncio.run(run_campaign(package, task, matrix_args=list(matrix or [])))
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    code = 0 if summary.get("all_pass") else 1
    raise typer.Exit(code=code)


@app.command("run")
def run_command(
    package: Annotated[
        Path,
        typer.Argument(help="Path to the Task Package root directory."),
    ],
    task: Annotated[
        str,
        typer.Option("--task", help="Task id that must match bora.yaml task_id."),
    ],
) -> None:
    """Run one foreground Attempt (v0.6 vertical slice). Evidence: L0 only."""
    import asyncio

    from bora.application.composition import build_run_task
    from bora.config.errors import ConfigError

    run_task = build_run_task()
    try:
        code, result, _details = asyncio.run(run_task(package, task))
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"runtime_error: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    # Prefer result.json written by use case when present (may include L1 fields).
    summary = {
        "status": result.status,
        "score": result.score,
        "assurance": result.assurance,
        "harness_kind": result.harness_kind,
        "runtime_kind": result.runtime_kind,
        "agent_invocations": result.agent_invocations,
        "evidence_path": result.evidence_path,
        "cleanup_warning": result.cleanup_warning,
    }
    if _details.get("l1"):
        summary["l1"] = _details["l1"]
    # Re-read assurance from details/result if use case overrode
    for key in ("assurance", "l1"):
        if key in _details:
            summary[key] = _details[key]
    typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    raise typer.Exit(code=code)


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
