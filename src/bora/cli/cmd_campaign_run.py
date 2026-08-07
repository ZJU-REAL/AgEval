"""CLI campaign and run commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Attach commands to the root Typer app."""

    @app.command("campaign")
    def campaign_command(
        package: Annotated[
            Path,
            typer.Argument(help="Database root (bora.database/1) for campaign matrix."),
        ],
        task: Annotated[
            str,
            typer.Option("--task", help="Member task id under the Database."),
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
            str,
            typer.Argument(
                help=(
                    "Database root path or registry ref "
                    "(<database_id>@<version> | <database_id>@sha256:<digest>)."
                ),
            ),
        ],
        task: Annotated[
            str | None,
            typer.Option(
                "--task",
                help=(
                    "Member task id (optional). Omit to run the full suite "
                    "(Spec 22). When set, only that member runs."
                ),
            ),
        ] = None,
        max_concurrent_tasks: Annotated[
            int | None,
            typer.Option(
                "--max-concurrent-tasks",
                help=(
                    "Max concurrent suite tasks (integer ≥1). Default 1 or Database "
                    "defaults.max_concurrent_tasks. Ignored when only one task runs."
                ),
            ),
        ] = None,
        set_overrides: Annotated[
            list[str] | None,
            typer.Option(
                "--set",
                help=(
                    "Repeatable override as <JSON Pointer>=<JSON value>, e.g. "
                    '`/parameters/active_profile="pi-mini"`. Allowlisted pointers only.'
                ),
            ),
        ] = None,
    ) -> None:
        """Run one member or a full Database suite (Application-layer task_id axis)."""
        import asyncio

        from bora.application.composition import build_run_task
        from bora.application.suite_run import execute_suite_run, plan_suite_run
        from bora.config.errors import ConfigError
        from bora.config.overrides import parse_set_override

        try:
            overrides: dict[str, object] = {}
            for raw in set_overrides or ():
                pointer, value = parse_set_override(raw)
                overrides[pointer] = value

            # Full suite when --task omitted; single task when provided.
            plan = plan_suite_run(
                package,
                task_id=task.strip() if task and str(task).strip() else None,
                max_concurrent_tasks=max_concurrent_tasks,
            )
            if len(plan.task_ids) == 1 and task and str(task).strip():
                # Preserve historical single-task JSON stdout shape.
                run_task = build_run_task()
                code, result, _details = asyncio.run(
                    run_task(package, plan.task_ids[0], overrides=overrides or None)
                )
                summary = {
                    "status": result.status,
                    "score": result.score,
                    "assurance": result.assurance,
                    "harness_kind": result.harness_kind,
                    "runtime_kind": result.runtime_kind,
                    "agent_invocations": result.agent_invocations,
                    "evidence_path": result.evidence_path,
                    "logs": result.logs or result.evidence_path,
                    "cleanup_warning": result.cleanup_warning,
                }
                if _details.get("l1"):
                    summary["l1"] = _details["l1"]
                for key in ("assurance", "l1", "logs"):
                    if key in _details:
                        summary[key] = _details[key]
                typer.echo(
                    json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                )
                raise typer.Exit(code=code)

            suite_summary = asyncio.run(execute_suite_run(plan, overrides=overrides or None))
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except typer.Exit:
            # Single-task path raises Exit with the real process code; do not remap to 2.
            raise
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"runtime_error: {type(exc).__name__}: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        typer.echo(
            json.dumps(suite_summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        raise typer.Exit(code=int(suite_summary.get("exit_code", 2)))
