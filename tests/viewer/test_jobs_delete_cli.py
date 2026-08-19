"""CLI ``ageval jobs delete`` uses the local Job delete use case."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from ageval.cli.main import app

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def _clean_db(tmp_path: Path) -> Path:
    db = tmp_path / "db"
    shutil.copytree(SUITE, db, ignore=shutil.ignore_patterns(".ageval"))
    return db


def test_cli_jobs_delete_requires_yes(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    evidence = db / ".ageval" / "runs" / "run_cli_single"
    evidence.mkdir(parents=True)
    (evidence / "result.json").write_text(
        json.dumps({"task_id": "alpha", "status": "PASS", "score": 1.0}) + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    preview = runner.invoke(
        app,
        ["jobs", "delete", "--local", str(db), "--job", "run_cli_single"],
    )
    assert preview.exit_code == 2
    payload = json.loads(preview.stdout)
    assert payload["kind"] == "single"
    assert payload["can_delete"] is True
    assert "refusing to delete without --yes" in preview.stderr
    assert evidence.is_dir()

    done = runner.invoke(
        app,
        ["jobs", "delete", "--local", str(db), "--job", "run_cli_single", "--yes"],
    )
    assert done.exit_code == 0, done.stdout + done.stderr
    out = json.loads(done.stdout)
    assert out["ok"] is True
    assert not evidence.exists()


def test_cli_jobs_delete_suite_cascade(tmp_path: Path) -> None:
    db = _clean_db(tmp_path)
    suite_dir = db / ".ageval" / "suite-runs" / "suite_cli"
    suite_dir.mkdir(parents=True)
    (suite_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema": "ageval.suite.summary/1",
                "suite_run_id": "suite_cli",
                "task_refs": [
                    {
                        "task_id": "alpha",
                        "run_id": "run_cli_a",
                        "attempt_run_ids": ["run_cli_a"],
                    }
                ],
                "tasks": [{"task_id": "alpha", "run_id": "run_cli_a"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    attempt = db / ".ageval" / "runs" / "run_cli_a"
    attempt.mkdir(parents=True)
    (attempt / "result.json").write_text(
        json.dumps({"task_id": "alpha", "status": "PASS", "score": 1.0}) + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    done = runner.invoke(
        app,
        ["jobs", "delete", "--local", str(db), "--job", "suite_cli", "--yes"],
    )
    assert done.exit_code == 0, done.stdout + done.stderr
    assert not suite_dir.exists()
    assert not attempt.exists()
