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
                help=(
                    "Axis as /parameters/...=[json-array] or "
                    "/bindings/<role>/model|executor|options/entry=[json-array] (#59)."
                ),
            ),
        ] = None,
        profiles: Annotated[
            Path | None,
            typer.Option(
                "--profiles",
                help="Alternate profiles.yaml replacing Database-root job bindings.",
            ),
        ] = None,
    ) -> None:
        """Foreground serial campaign over a parameter matrix (v0.11)."""
        import asyncio

        from bora.application.composition import build_campaign_runner
        from bora.config.errors import ConfigError

        run_campaign = build_campaign_runner()
        try:
            summary = asyncio.run(
                run_campaign(
                    package,
                    task,
                    matrix_args=list(matrix or []),
                    profiles_path=profiles,
                )
            )
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
                    "Max concurrent suite work units (integer ≥1). Default 1 or Database "
                    "defaults.max_concurrent_tasks. Speeds wall time only; does not change "
                    "n_attempts or pass/fail. Forced to 1 when a single task runs once."
                ),
            ),
        ] = None,
        n_attempts: Annotated[
            int | None,
            typer.Option(
                "--n-attempts",
                "-k",
                help=(
                    "Always-k: independent Attempts per task (integer ≥1, default 1). "
                    "CLI/job only — not a task.yaml field, not part of config_fingerprint. "
                    "Feeds pass@k / pass^k job metrics."
                ),
            ),
        ] = None,
        resume_suite: Annotated[
            str | None,
            typer.Option(
                "--resume-suite",
                help=(
                    "Resume an existing suite_run_id under .bora/suite-runs/. "
                    "Skips finished (task_id, attempt_index) units, appends new Attempts, "
                    "recomputes pass@k / pass^k. Combine with --task to top up one task."
                ),
            ),
        ] = None,
        set_overrides: Annotated[
            list[str] | None,
            typer.Option(
                "--set",
                help=(
                    "Repeatable override as <JSON Pointer>=<JSON value>, e.g. "
                    '`/parameters/active_profile="solver"` or '
                    '`/bindings/solver/options/entry="pi"`. Allowlisted only.'
                ),
            ),
        ] = None,
        profiles: Annotated[
            Path | None,
            typer.Option(
                "--profiles",
                help="Alternate profiles.yaml replacing Database-root job bindings.",
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

            k = n_attempts if n_attempts is not None else 1
            resume_id = resume_suite.strip() if resume_suite and str(resume_suite).strip() else None

            # Full suite when --task omitted; single task when provided.
            plan = plan_suite_run(
                package,
                task_id=task.strip() if task and str(task).strip() else None,
                max_concurrent_tasks=max_concurrent_tasks,
                n_attempts=k,
                suite_run_id=resume_id,
            )
            # Historical single-task JSON only when k==1 and not resuming.
            if (
                len(plan.task_ids) == 1
                and task
                and str(task).strip()
                and plan.n_attempts == 1
                and resume_id is None
            ):
                run_task = build_run_task()
                code, result, _details = asyncio.run(
                    run_task(
                        package,
                        plan.task_ids[0],
                        overrides=overrides or None,
                        profiles_path=profiles,
                    )
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

            import os
            import sys

            from bora.control.store import ControlStore

            # Register suite job for bora status / bora cancel (D4).
            control_path = Path.cwd() / ".bora" / "control.db"
            cs = ControlStore(control_path)
            cs.put(
                plan.suite_run_id,
                status="running",
                owner="cli-run",
                payload={
                    "kind": "suite",
                    "suite_run_id": plan.suite_run_id,
                    "database_root": str(plan.database_root),
                    "pid": os.getpid(),
                    "n_attempts": plan.n_attempts,
                    "task_ids": list(plan.task_ids),
                    "max_concurrent_tasks": plan.max_concurrent_tasks,
                },
            )

            def _progress(ev: dict) -> None:
                # Terminal progress on stderr; final JSON stays on stdout.
                kind = str(ev.get("type") or "")
                done = ev.get("done")
                total = ev.get("total")
                if kind == "suite_start":
                    sys.stderr.write(
                        f"suite {plan.suite_run_id}: start "
                        f"todo={ev.get('todo')} total={total} "
                        f"(cancel: bora cancel {plan.suite_run_id})\n"
                    )
                elif kind == "unit_start":
                    sys.stderr.write(
                        f"[{done}/{total}] start {ev.get('task_id')} "
                        f"attempt={ev.get('attempt_index')}\n"
                    )
                elif kind == "unit_done":
                    sys.stderr.write(
                        f"[{done}/{total}] done  {ev.get('task_id')} "
                        f"attempt={ev.get('attempt_index')} "
                        f"{ev.get('status')}"
                        + (f" {ev.get('duration')}" if ev.get("duration") else "")
                        + "\n"
                    )
                elif kind == "suite_complete":
                    sys.stderr.write(
                        f"suite complete exit={ev.get('exit_code')} done={done}/{total}\n"
                    )
                elif kind == "suite_cancelled":
                    sys.stderr.write(
                        f"suite cancelled done={done}/{total} skipped={ev.get('cancelled_units')}\n"
                    )
                sys.stderr.flush()

            suite_summary = asyncio.run(
                execute_suite_run(
                    plan,
                    overrides=overrides or None,
                    profiles_path=profiles,
                    resume=resume_id is not None,
                    on_progress=_progress,
                )
            )
            final_status = (
                "cancelled"
                if suite_summary.get("cancelled")
                else ("completed" if int(suite_summary.get("exit_code", 2)) == 0 else "failed")
            )
            cs.put(
                plan.suite_run_id,
                status=final_status,
                owner="cli-run",
                payload={
                    "kind": "suite",
                    "suite_run_id": plan.suite_run_id,
                    "database_root": str(plan.database_root),
                    "exit_code": suite_summary.get("exit_code"),
                    "summary_path": suite_summary.get("summary_path"),
                    "n_attempts": plan.n_attempts,
                    "cancelled": bool(suite_summary.get("cancelled")),
                },
            )
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
