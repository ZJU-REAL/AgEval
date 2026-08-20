"""Standalone Attempt upload projects environment from lock, not a suite wrap."""

from __future__ import annotations

import json
from pathlib import Path

from ageval.application.registry_ops.results_command import _attempt_job_fields


def test_attempt_job_fields_reads_lock_environment(tmp_path: Path) -> None:
    run = tmp_path / "attempt_x"
    run.mkdir()
    (run / "lock.json").write_text(
        json.dumps(
            {
                "task_id": "terminal-jsonl-agg",
                "environment": "e2b",
                "job_overlay": {
                    "environment": "e2b",
                    "agent_profiles": {
                        "solver": {"executor": "dsh", "model": "glm-5.2"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    fields = _attempt_job_fields(run, {"kind": "e2b", "score": 1.0, "status": "PASS"})
    assert fields["environment"] == "e2b"
    assert fields["task_id"] == "terminal-jsonl-agg"
    assert fields["model_label"] == "glm-5.2"
    assert fields["score"] == 1.0
