"""CLI/application slot append uploads one run without --replace."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bora.application.registry_ops.results_command import ResultsCommands
from bora.config.errors import ConfigError


def _seed(db: Path, *, suite_id: str = "suite1") -> None:
    (db / "bora.yaml").write_text(
        "format: bora.database/1\ndatabase_id: test/db\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    suite_dir = db / ".bora" / "suite-runs" / suite_id
    suite_dir.mkdir(parents=True)
    suite_dir.joinpath("summary.json").write_text(
        """{
  "schema": "bora.suite.summary/1",
  "suite_run_id": "suite1",
  "database_id": "test/db",
  "database_version": "0.1.0",
  "exit_code": 0,
  "config_fingerprint": "sha256:fp",
  "amended": true,
  "attempts": [
    {
      "task_id": "hello",
      "attempt_index": 0,
      "status": "PASS",
      "score": 1.0,
      "run_id": "newrun",
      "previous": [
        {"run_id": "oldrun", "status": "ERROR", "score": null, "attempt_index": 0}
      ]
    }
  ],
  "tasks": [{"task_id": "hello", "status": "PASS", "score": 1.0, "run_id": "newrun"}],
  "task_refs": [
    {
      "task_id": "hello",
      "status": "PASS",
      "score": 1.0,
      "run_id": "newrun",
      "previous": [
        {"run_id": "oldrun", "status": "ERROR", "score": null, "attempt_index": 0}
      ]
    }
  ],
  "metrics": {
    "pass_rate": 1.0,
    "mean_score": 1.0,
    "n_tasks": 1,
    "n_pass": 1,
    "n_fail": 0,
    "n_error": 0,
    "missing_score_as": 0.0
  }
}
""",
        encoding="utf-8",
    )
    for rid in ("newrun", "oldrun"):
        run_dir = db / ".bora" / "runs" / rid
        run_dir.mkdir(parents=True)
        run_dir.joinpath("result.json").write_text(
            f'{{"status": "PASS", "task_id": "hello", "run_id": "{rid}"}}\n',
            encoding="utf-8",
        )


def test_append_slot_uploads_attempt_and_patches_suite(tmp_path: Path) -> None:
    db = tmp_path / "db"
    db.mkdir()
    _seed(db)
    captured: dict[str, Any] = {}
    mock = MagicMock()
    mock.upload_attempt.return_value = {"run_id": "newrun", "ok": True}
    mock.append_suite_slot.side_effect = lambda **kw: (
        captured.update(kw)
        or {
            "suite_run_id": kw["suite_run_id"],
            "task_refs": kw["task_refs"],
            "metrics": kw["metrics"],
            "pass_rate": 1.0,
            "mean_score": 1.0,
            "amended": True,
            "note": "per-task evaluator verdicts only; no suite-level PASS",
        }
    )
    cmds = ResultsCommands(client_factory=lambda **_kw: mock)
    out = cmds.append_suite_slot_result(db, suite_run_id="suite1", task_id="hello")
    assert out["appended"] is True
    assert out["run_id"] == "newrun"
    assert captured["run_id"] == "newrun"
    assert captured["task_id"] == "hello"
    assert captured["task_refs"][0]["previous"][0]["run_id"] == "oldrun"
    mock.upload_suite.assert_not_called()
    mock.upload_attempt.assert_called()
    assert mock.upload_attempt.call_args.kwargs.get("replace") is False


def test_append_slot_refuses_foreign_run(tmp_path: Path) -> None:
    db = tmp_path / "db"
    db.mkdir()
    _seed(db)
    (db / ".bora" / "runs" / "other").mkdir(parents=True)
    (db / ".bora" / "runs" / "other" / "result.json").write_text("{}\n", encoding="utf-8")
    cmds = ResultsCommands(client_factory=lambda **_kw: MagicMock())
    with pytest.raises(ConfigError, match="current pointer"):
        cmds.append_suite_slot_result(db, suite_run_id="suite1", task_id="hello", run_id="other")
