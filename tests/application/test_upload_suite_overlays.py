"""upload-suite keeps overlay paths only and fail-closes on secret files."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ageval.application.registry_ops.results_command import ResultsCommands
from ageval.config.errors import ConfigError


def _write_db(
    tmp: Path,
    *,
    overlay_text: str,
    include_overlays: bool = True,
) -> tuple[Path, str]:
    db = tmp / "db"
    db.mkdir()
    (db / "ageval.yaml").write_text(
        "format: ageval.dataset/1\ndataset_id: example/overlays\nversion: '0.1.0'\n"
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    (db / "overlays").mkdir()
    (db / "overlays" / "cfg.json").write_text(overlay_text, encoding="utf-8")
    # Large tree that must not ride the suite archive.
    blob = db / "overlays" / "skills" / "jsonl-agg"
    blob.mkdir(parents=True)
    (blob / "SKILL.md").write_text("# skill\n" + ("x" * 4096), encoding="utf-8")
    suite_run_id = "suite_overlays"
    suite_dir = db / ".ageval" / "suite-runs" / suite_run_id
    suite_dir.mkdir(parents=True)
    binding: dict[str, Any] = {
        "executor": "acp",
        "extensions": [{"plugin": "acp", "options": {"entry": "grok-build"}}],
        "model": "m",
    }
    if include_overlays:
        binding["overlays"] = ["overlays/cfg.json", "overlays/skills/jsonl-agg"]
    summary = {
        "schema": "ageval.suite.summary/1",
        "suite_run_id": suite_run_id,
        "dataset_id": "example/overlays",
        "dataset_version": "0.1.0",
        "exit_code": 0,
        "metrics": {"pass_rate": 1.0, "mean_score": 1.0, "n_tasks": 1},
        "task_refs": [{"task_id": "t", "status": "PASS", "score": 1.0}],
        "job_overlay": {"bindings": {"solver": binding}},
    }
    (suite_dir / "summary.json").write_text(json.dumps(summary) + "\n", encoding="utf-8")
    return db, suite_run_id


def _cmds() -> tuple[ResultsCommands, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def fake_upload_suite(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        archive = kwargs.get("archive")
        if archive is not None:
            captured["archive_bytes"] = Path(archive).read_bytes()
        return {
            "suite_run_id": kwargs["suite_run_id"],
            "dataset_id": kwargs["dataset_id"],
            "dataset_version": kwargs["dataset_version"],
            "pass_rate": kwargs["pass_rate"],
            "mean_score": kwargs["mean_score"],
            "metrics": kwargs["metrics"],
            "task_refs": kwargs["task_refs"],
            "blob_digest": kwargs["blob_digest"],
            "size": kwargs["size"],
            "job_overlay": kwargs.get("job_overlay"),
            "note": "per-task evaluator verdicts only; no suite-level PASS",
        }

    mock_client = MagicMock()
    mock_client.upload_suite.side_effect = lambda **kw: fake_upload_suite(**kw)
    return ResultsCommands(client_factory=lambda **_kw: mock_client), captured


def test_upload_suite_sends_overlay_paths_not_bytes(tmp_path: Path) -> None:
    db, suite_id = _write_db(tmp_path, overlay_text='{"apiKey": "{env:litellm_api_key}"}')
    cmds, captured = _cmds()
    out = cmds.upload_suite_result(db, suite_run_id=suite_id)
    assert out["ok"] is True
    overlay = captured["job_overlay"]
    assert overlay["bindings"]["solver"]["overlays"] == [
        "overlays/cfg.json",
        "overlays/skills/jsonl-agg",
    ]
    dumped = json.dumps(overlay)
    assert "{env:litellm_api_key}" not in dumped
    assert "# skill" not in dumped
    with tarfile.open(fileobj=io.BytesIO(captured["archive_bytes"]), mode="r:gz") as tar:
        names = tar.getnames()
    assert names
    assert all(name == ".ageval" or name.startswith(".ageval/") for name in names)
    assert not any("overlays/cfg.json" in name for name in names)
    assert not any("overlays/skills/" in name for name in names)
    assert any(name.endswith("summary.json") for name in names)
    overlay_tree_bytes = sum(p.stat().st_size for p in (db / "overlays").rglob("*") if p.is_file())
    assert overlay_tree_bytes > 4096
    assert captured["size"] < overlay_tree_bytes


def test_upload_suite_rejects_secret_overlay_file(tmp_path: Path) -> None:
    db, suite_id = _write_db(tmp_path, overlay_text="-----BEGIN PRIVATE KEY-----\nabc\n")
    cmds, _captured = _cmds()
    with pytest.raises(ConfigError) as ei:
        cmds.upload_suite_result(db, suite_run_id=suite_id)
    assert ei.value.error_code == "invalid_package"
    assert "secret" in str(ei.value).lower()


def test_upload_suite_omit_overlays_skips_scan(tmp_path: Path) -> None:
    db, suite_id = _write_db(
        tmp_path,
        overlay_text="-----BEGIN PRIVATE KEY-----\nabc\n",
        include_overlays=False,
    )
    cmds, captured = _cmds()
    out = cmds.upload_suite_result(db, suite_run_id=suite_id)
    assert out["ok"] is True
    assert "overlays" not in captured["job_overlay"]["bindings"]["solver"]
