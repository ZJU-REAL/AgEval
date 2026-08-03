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
    set_overrides: Annotated[
        list[str] | None,
        typer.Option(
            "--set",
            help=(
                "Repeatable override as <JSON Pointer>=<JSON value>, e.g. "
                "`/parameters/active_profile=\"pi-mini\"`. Allowlisted pointers only."
            ),
        ),
    ] = None,
) -> None:
    """Run one foreground Attempt (v0.6 vertical slice). Evidence: L0 only."""
    import asyncio

    from bora.application.composition import build_run_task
    from bora.config.errors import ConfigError
    from bora.config.load_and_lock import parse_set_override

    run_task = build_run_task()
    try:
        overrides: dict[str, object] = {}
        for raw in set_overrides or ():
            pointer, value = parse_set_override(raw)
            overrides[pointer] = value
        code, result, _details = asyncio.run(
            run_task(package, task, overrides=overrides or None)
        )
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
        "logs": result.logs or result.evidence_path,
        "cleanup_warning": result.cleanup_warning,
    }
    if _details.get("l1"):
        summary["l1"] = _details["l1"]
    # Re-read assurance from details/result if use case overrode
    for key in ("assurance", "l1", "logs"):
        if key in _details:
            summary[key] = _details[key]
    typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    raise typer.Exit(code=code)


@app.command("status")
def status_command(
    run_id: Annotated[str, typer.Argument(help="Run id from ControlStore.")],
    store: Annotated[
        Path | None,
        typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
    ] = None,
) -> None:
    """Query durable Run control record (v0.12)."""
    from bora.control.store import ControlStore

    path = store or (Path.cwd() / ".bora" / "control.db")
    rec = ControlStore(path).get(run_id)
    if rec is None:
        typer.echo(json.dumps({"ok": False, "error": "unknown_run", "run_id": run_id}))
        raise typer.Exit(code=2)
    typer.echo(json.dumps({"ok": True, **rec}, sort_keys=True, separators=(",", ":")))


@app.command("cancel")
def cancel_command(
    run_id: Annotated[str, typer.Argument(help="Run id to cancel.")],
    store: Annotated[
        Path | None,
        typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
    ] = None,
) -> None:
    """Mark a durable Run as cancelled and SIGTERM stored pid when present (v0.12)."""
    import os
    import signal

    from bora.control.store import ControlStore

    path = store or (Path.cwd() / ".bora" / "control.db")
    cs = ControlStore(path)
    rec = cs.get(run_id)
    if rec is None:
        typer.echo(json.dumps({"ok": False, "error": "unknown_run", "run_id": run_id}))
        raise typer.Exit(code=2)
    payload = dict(rec.get("payload") or {})
    killed = False
    pid = payload.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            killed = False
    version = cs.put(
        run_id,
        status="cancelled",
        owner=str(rec.get("owner") or "cli"),
        payload={**payload, "cancel_requested": True, "sigterm_sent": killed},
    )
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "run_id": run_id,
                "status": "cancelled",
                "version": version,
                "sigterm_sent": killed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command("submit")
def submit_command(
    package: Annotated[Path, typer.Argument(help="Task Package root.")],
    task: Annotated[str, typer.Option("--task", help="Task id.")],
    store: Annotated[
        Path | None,
        typer.Option("--store", help="ControlStore sqlite path (default .bora/control.db)."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Block until Attempt finishes (default: detach child)."),
    ] = False,
) -> None:
    """Submit a Run with durable ControlStore record (v0.12).

    Default: spawn a detached child process for ``bora run`` and return run_id.
    ``bora status`` / ``bora cancel`` observe or fence the record (cancel sends SIGTERM
    to stored pid when present).
    """
    import os
    import subprocess
    import uuid

    from bora.control.store import ControlStore

    path = (store or (Path.cwd() / ".bora" / "control.db")).resolve()
    cs = ControlStore(path)
    run_id = f"run_{uuid.uuid4().hex}"
    if wait:
        import asyncio

        from bora.application.composition import build_run_task

        cs.put(
            run_id,
            status="running",
            owner="cli-submit",
            payload={"package": str(package), "task": task, "mode": "wait"},
        )
        try:
            code, result, _details = asyncio.run(build_run_task()(package, task))
            status = "completed" if code == 0 else "failed"
            cs.put(
                run_id,
                status=status,
                owner="cli-submit",
                payload={
                    "package": str(package),
                    "task": task,
                    "exit_code": code,
                    "result_status": result.status,
                    "evidence_path": result.evidence_path,
                },
            )
        except Exception as exc:  # noqa: BLE001
            cs.put(
                run_id,
                status="failed",
                owner="cli-submit",
                payload={"error": f"{type(exc).__name__}: {exc}"},
            )
            typer.echo(json.dumps({"ok": False, "run_id": run_id, "error": str(exc)}))
            raise typer.Exit(code=2) from exc
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "status": status,
                    "exit_code": code,
                    "result_status": result.status,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise typer.Exit(code=code)

    # Detached child: re-exec production CLI for the Attempt.
    log_path = path.parent / f"{run_id}.log"
    child_env = os.environ.copy()
    child_env["BORA_CONTROL_RUN_ID"] = run_id
    child_env["BORA_CONTROL_STORE"] = str(path)
    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(package.resolve()),
            "--task",
            task,
        ],
        cwd=str(Path.cwd()),
        env=child_env,
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    cs.put(
        run_id,
        status="running",
        owner="cli-submit",
        payload={
            "package": str(package.resolve()),
            "task": task,
            "pid": proc.pid,
            "log_path": str(log_path),
            "mode": "detach",
        },
    )
    typer.echo(
        json.dumps(
            {"ok": True, "run_id": run_id, "status": "running", "pid": proc.pid, "detached": True},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


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
