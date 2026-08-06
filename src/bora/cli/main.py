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
        "CLI path arguments are Database roots (`bora.database/1`). "
        "Use `--task <id>` to select a member under `tasks/<id>/task.yaml`. "
        "List members with `bora tasks <database>`."
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
                "`/parameters/active_profile=\"pi-mini\"`. Allowlisted pointers only."
            ),
        ),
    ] = None,
) -> None:
    """Run one member or a full Database suite (Application-layer task_id axis)."""
    import asyncio

    from bora.application.composition import build_run_task
    from bora.application.suite_run import execute_suite_run, plan_suite_run
    from bora.config.errors import ConfigError
    from bora.config.load_and_lock import parse_set_override

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

        suite_summary = asyncio.run(
            execute_suite_run(plan, overrides=overrides or None)
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


@app.command("evidence")
def evidence_export_command(
    evidence_root: Annotated[
        Path,
        typer.Argument(help="Attempt evidence root (Result.logs path)."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Destination directory for versioned export."),
    ],
) -> None:
    """Export sealed trajectory as re-redacted copy (v0.17). Does not change score."""
    from bora.evidence.export import export_trajectory

    result = export_trajectory(evidence_root, out)
    typer.echo(
        json.dumps(
            {
                "ok": result.ok,
                "export_path": result.export_path,
                "invocation_count": result.invocation_count,
                "error": result.error,
                "schema": "bora.trajectory.export/1",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    raise typer.Exit(code=0 if result.ok else 2)


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
    package: Annotated[Path, typer.Argument(help="Database root (bora.database/1).")],
    task: Annotated[str, typer.Option("--task", help="Member task id.")],
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


@app.command("executors")
def executors_command(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Include capability detail (tools/session + default credential env names).",
        ),
    ] = False,
) -> None:
    """List supported agent executor kinds and whether host binaries are on PATH.

    Thin CLI: inventory logic lives in ``bora.adapters.executor_inventory``.
    """
    from bora.adapters.executor_inventory import build_executor_inventory

    summary = build_executor_inventory(verbose=verbose)
    typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


@app.command("publish")
def publish_command(
    database: Annotated[
        Path,
        typer.Argument(help="Local Database root to publish (bora.database/1)."),
    ],
    public: Annotated[
        bool,
        typer.Option(
            "--public",
            help="Create a public release (default: private).",
        ),
    ] = False,
    registry_url: Annotated[
        str | None,
        typer.Option(
            "--registry-url",
            help="Override BORA_REGISTRY_URL / credentials file registry URL.",
        ),
    ] = None,
) -> None:
    """Publish a local Database package to the configured Registry (Spec 21)."""
    from bora.application.publish_command import publish_database
    from bora.config.errors import ConfigError

    try:
        summary = publish_database(
            database,
            public=public,
            registry_url=registry_url,
        )
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"invalid_package: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@app.command("login")
def login_command(
    registry_url: Annotated[
        str | None,
        typer.Option(
            "--registry-url",
            help="Override BORA_REGISTRY_URL / credentials file registry URL.",
        ),
    ] = None,
) -> None:
    """GitHub Device Flow login; write ``~/.bora/credentials`` (mode 0600)."""
    from bora.application.login_command import login_registry
    from bora.config.errors import ConfigError

    try:
        summary = login_registry(registry_url=registry_url)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


registry_app = typer.Typer(
    name="registry",
    help="List/show Database packages on the configured Registry.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(registry_app, name="registry")


@registry_app.command("list")
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


@registry_app.command("show")
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


cache_app = typer.Typer(
    name="cache",
    help="Inspect / purge local verified package cache.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(cache_app, name="cache")


@cache_app.command("list")
def cache_list_command() -> None:
    """List verified entries under BORA_CACHE_ROOT / .bora/cache."""
    from bora.application.registry_list_command import cache_list

    summary = cache_list()
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@cache_app.command("path")
def cache_path_command(
    ref: Annotated[
        str,
        typer.Argument(help="Package ref already present in the local cache."),
    ],
) -> None:
    """Print filesystem path of a verified cache entry."""
    from bora.application.registry_list_command import cache_path
    from bora.config.errors import ConfigError

    try:
        summary = cache_path(ref)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@cache_app.command("purge")
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
    from bora.application.registry_list_command import cache_purge
    from bora.config.errors import ConfigError

    try:
        summary = cache_purge(target, yes=yes)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


results_app = typer.Typer(
    name="results",
    help="Upload / fetch Attempt run evidence bundles (results store).",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(results_app, name="results")


@results_app.command("upload")
def results_upload_command(
    database: Annotated[
        Path,
        typer.Argument(help="Local Database root containing .bora/runs/<run_id>."),
    ],
    run: Annotated[
        str,
        typer.Option("--run", help="Attempt run_id under .bora/runs/."),
    ],
    public: Annotated[
        bool,
        typer.Option("--public", help="Create a public result (default: private)."),
    ] = False,
    registry_url: Annotated[
        str | None,
        typer.Option("--registry-url", help="Override registry / results URL."),
    ] = None,
) -> None:
    """Upload a sealed Attempt directory to the results store."""
    from bora.application.results_command import upload_attempt_result
    from bora.config.errors import ConfigError

    try:
        summary = upload_attempt_result(
            database,
            run_id=run,
            public=public,
            registry_url=registry_url,
        )
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"invalid_package: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@results_app.command("get")
def results_get_command(
    run_id: Annotated[
        str,
        typer.Argument(help="Attempt run_id previously uploaded."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory to extract the result bundle into."),
    ],
    registry_url: Annotated[
        str | None,
        typer.Option("--registry-url", help="Override registry / results URL."),
    ] = None,
) -> None:
    """Download and extract an Attempt result bundle."""
    from bora.application.results_command import get_attempt_result
    from bora.config.errors import ConfigError

    try:
        summary = get_attempt_result(run_id, out_dir=out, registry_url=registry_url)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@results_app.command("list")
def results_list_command(
    database_id: Annotated[
        str | None,
        typer.Option("--database-id", help="Filter by database_id."),
    ] = None,
    registry_url: Annotated[
        str | None,
        typer.Option("--registry-url", help="Override registry / results URL."),
    ] = None,
) -> None:
    """List Attempt results visible to the current credentials."""
    from bora.application.results_command import list_attempt_results
    from bora.config.errors import ConfigError

    try:
        summary = list_attempt_results(
            database_id=database_id,
            registry_url=registry_url,
        )
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@app.command("tasks")
def tasks_command(
    database: Annotated[
        Path,
        typer.Argument(help="Path to the Database root directory (bora.database/1)."),
    ],
) -> None:
    """List member task ids under a Database (fail closed on empty or id mismatch)."""
    from bora.config.database import list_tasks, load_database_manifest
    from bora.config.errors import ConfigError

    try:
        manifest = load_database_manifest(database)
        ids = list_tasks(database, manifest=manifest)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"invalid_package: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    payload = {
        "database_id": manifest.database_id,
        "version": manifest.version,
        "tasks": ids,
        "count": len(ids),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


@app.command("lock")
def lock_command(
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
            help="Member task id (required). Must match tasks/<id>/task.yaml task_id.",
        ),
    ] = None,
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
    """Resolve a Database member, lock its task.yaml; print a deterministic JSON summary."""
    if task is None or not str(task).strip():
        typer.echo(
            "invalid_override: --task is required "
            "(suite-wide lock without --task is not supported)",
            err=True,
        )
        raise typer.Exit(code=2)

    use_case = build_lock_command()
    try:
        summary = use_case.run(
            database_root=package,
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
