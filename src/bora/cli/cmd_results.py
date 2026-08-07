"""CLI results upload/get/list and suite commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Create and mount the ``results`` sub-app."""

    sub = typer.Typer(
        name="results",
        help="Upload / fetch Attempt and suite/job result bundles (results store).",
        no_args_is_help=True,
        add_completion=False,
    )

    @sub.command("upload")
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

    @sub.command("get")
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

    @sub.command("list")
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

    @sub.command("upload-suite")
    def results_upload_suite_command(
        database: Annotated[
            Path,
            typer.Argument(help="Local Database root containing .bora/suite-runs/<id>."),
        ],
        suite_run: Annotated[
            str,
            typer.Option("--suite-run", help="Suite run id under .bora/suite-runs/."),
        ],
        public: Annotated[
            bool,
            typer.Option("--public", help="Create a public suite result (default: private)."),
        ] = False,
        agent: Annotated[
            str,
            typer.Option("--agent", help="Optional agent label for leaderboard meta."),
        ] = "",
        model: Annotated[
            str,
            typer.Option("--model", help="Optional model label for leaderboard meta."),
        ] = "",
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry / results URL."),
        ] = None,
    ) -> None:
        """Upload a suite/job result row (metrics + task refs; no suite PASS)."""
        from bora.application.results_command import upload_suite_result
        from bora.config.errors import ConfigError

        try:
            summary = upload_suite_result(
                database,
                suite_run_id=suite_run,
                public=public,
                agent_label=agent,
                model_label=model,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"invalid_package: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("get-suite")
    def results_get_suite_command(
        suite_run_id: Annotated[
            str,
            typer.Argument(help="Suite run id (registry or local)."),
        ],
        out: Annotated[
            Path | None,
            typer.Option("--out", help="Optional directory to extract the suite archive into."),
        ] = None,
        local: Annotated[
            Path | None,
            typer.Option(
                "--local",
                help="Read from local Database .bora/suite-runs/ (no registry).",
            ),
        ] = None,
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry / results URL."),
        ] = None,
    ) -> None:
        """Get suite/job result meta; optionally extract archive from registry."""
        from bora.application.results_command import get_suite_result
        from bora.config.errors import ConfigError

        try:
            summary = get_suite_result(
                suite_run_id,
                out_dir=out,
                local=local,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    @sub.command("list-suites")
    def results_list_suites_command(
        database_id: Annotated[
            str | None,
            typer.Option("--database-id", help="Filter by database_id."),
        ] = None,
        local: Annotated[
            Path | None,
            typer.Option(
                "--local",
                help="List local Database .bora/suite-runs/ (no registry).",
            ),
        ] = None,
        registry_url: Annotated[
            str | None,
            typer.Option("--registry-url", help="Override registry / results URL."),
        ] = None,
    ) -> None:
        """List suite/job results (registry or --local Database path)."""
        from bora.application.results_command import list_suite_results
        from bora.config.errors import ConfigError

        try:
            summary = list_suite_results(
                database_id=database_id,
                local=local,
                registry_url=registry_url,
            )
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    app.add_typer(sub, name="results")
