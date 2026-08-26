"""TTY recap and plain progress for ``ageval run`` (no JSON blob)."""

from __future__ import annotations

import io
from pathlib import Path

from ageval.cli.run_output import (
    RunProgress,
    dataset_label,
    format_attempt_recap,
    format_duration_ms,
    format_suite_recap,
    use_json_stdout,
)


def test_use_json_stdout_force_and_pipe() -> None:
    assert use_json_stdout(force_json=True, stream=io.StringIO()) is True
    assert use_json_stdout(force_json=False, stream=io.StringIO()) is True


def test_dataset_label_joins_version() -> None:
    assert dataset_label("official/demo", "0.1.0") == "official/demo@0.1.0"
    assert dataset_label("official/demo", "") == "official/demo"


def test_format_duration_ms_seconds() -> None:
    assert format_duration_ms(12) == "12ms"
    assert format_duration_ms(8100) == "8.1s"
    assert format_duration_ms(12_400) == "12.4s"


def test_suite_recap_omits_json_payload(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("{}\n", encoding="utf-8")
    text = format_suite_recap(
        {
            "suite_run_id": "863b8ee9",
            "dataset_id": "official/demo",
            "dataset_version": "0.1.0",
            "n_attempts": 1,
            "exit_code": 0,
            "summary_path": str(summary_path),
            "counts": {"pass": 2, "fail": 0, "error": 0, "skipped": 0},
            "task_ids": ["tau2-dialog-min", "terminal-jsonl-agg"],
            "tasks": [
                {"task_id": "tau2-dialog-min", "status": "PASS", "attempt_index": 0},
                {"task_id": "terminal-jsonl-agg", "status": "PASS", "attempt_index": 0},
            ],
            "actors_summary": [{"profile_id": "solver", "model": "secret-looking"}],
        },
        dataset_root=tmp_path,
    )
    first, counts, *_rest = text.splitlines()
    assert first and set(first) <= {"─"}
    assert counts == "2/2 PASS   exit=0"
    assert "tau2-dialog-min" not in text
    assert "terminal-jsonl-agg" not in text
    assert "suite 863b8ee9" not in text
    assert "summary  " in text
    assert "ageval view " in text
    assert "ageval results upload-suite " in text
    assert "sha256_" not in text.split("ageval view ", 1)[-1].splitlines()[0]
    assert "--suite-run 863b8ee9" in text
    assert "actors_summary" not in text
    assert "secret-looking" not in text
    assert "{" not in text


def test_suite_recap_k_and_fail() -> None:
    text = format_suite_recap(
        {
            "suite_run_id": "abcd1234",
            "dataset_id": "test/suite-min",
            "dataset_version": "0.1.0",
            "n_attempts": 2,
            "exit_code": 1,
            "counts": {"pass": 0, "fail": 1, "error": 0, "skipped": 0},
            "task_ids": ["alpha"],
            "attempts": [
                {"task_id": "alpha", "attempt_index": 0, "status": "PASS"},
                {"task_id": "alpha", "attempt_index": 1, "status": "FAIL"},
            ],
        },
        dataset_root=".",
    )
    assert "alpha" not in text
    assert "FAIL" in text
    assert "k=2" in text
    first, counts, *_rest = text.splitlines()
    assert first and set(first) <= {"─"}
    assert counts == "0/1 PASS   1 FAIL   k=2   exit=1"


def test_attempt_recap_has_logs_and_next() -> None:
    text = format_attempt_recap(
        {
            "status": "PASS",
            "logs": "runs/abc",
            "evidence_path": "runs/abc",
        },
        task_id="alpha",
        dataset_root="examples/core",
        duration="1.2s",
    )
    assert text.startswith("task alpha  PASS  1.2s\n")
    assert "logs     " in text
    assert "ageval view " in text
    assert "{" not in text


def test_plain_progress_aligns_done_line() -> None:
    buf = io.StringIO()
    clock = iter([0.0, 1.25, 1.25])
    progress = RunProgress(
        suite_run_id="863b8ee9",
        dataset_label="official/demo@0.1.0",
        stderr=buf,
        use_bar=False,
        use_color=False,
        monotonic=lambda: next(clock),
    )
    progress.handle({"type": "suite_start", "todo": 1, "total": 1, "done": 0})
    progress.handle(
        {
            "type": "unit_start",
            "task_id": "tau2-dialog-min",
            "attempt_index": 0,
            "done": 0,
            "total": 1,
        }
    )
    progress.handle(
        {
            "type": "unit_done",
            "task_id": "tau2-dialog-min",
            "attempt_index": 0,
            "status": "PASS",
            "done": 1,
            "total": 1,
        }
    )
    progress.close()
    text = buf.getvalue()
    assert "suite 863b8ee9  official/demo@0.1.0" in text
    assert "cancel: ageval cancel 863b8ee9" in text
    assert "start  tau2-dialog-min" in text
    assert "PASS" in text
    assert "1.2s" in text
    assert progress.elapsed_labels()[("tau2-dialog-min", 0)] == "1.2s"


def test_unit_lines_align_status_right_duration_left() -> None:
    buf = io.StringIO()
    clock = iter([0.0, 43.2, 43.2, 111.2])
    progress = RunProgress(
        suite_run_id="ca096a6f",
        dataset_label="official/demo@0.1.0",
        stderr=buf,
        use_bar=False,
        use_color=False,
        monotonic=lambda: next(clock),
        task_ids=["tau2-dialog-min", "terminal-jsonl-agg"],
    )
    progress.handle({"type": "suite_start", "todo": 2, "total": 2, "done": 0})
    for tid in ("tau2-dialog-min", "terminal-jsonl-agg"):
        progress.handle(
            {
                "type": "unit_start",
                "task_id": tid,
                "attempt_index": 0,
                "done": 0,
                "total": 2,
            }
        )
        progress.handle(
            {
                "type": "unit_done",
                "task_id": tid,
                "attempt_index": 0,
                "status": "PASS",
                "done": 1,
                "total": 2,
            }
        )
    progress.close()
    rows = [ln for ln in buf.getvalue().splitlines() if "PASS" in ln]
    assert len(rows) == 2
    pass_at = rows[0].index("PASS")
    assert rows[1].index("PASS") == pass_at
    time_at = pass_at + len("PASS") + 2
    assert rows[0][time_at:].startswith("43.2s")
    assert rows[1][time_at:].startswith("1m 08s")
    assert rows[0][pass_at - 1] == " "
    assert rows[1][pass_at - 1] == " "


def test_suite_recap_view_uses_ref_for_cache_root(tmp_path: Path) -> None:
    cache_root = (
        tmp_path
        / ".ageval"
        / "cache"
        / "datasets"
        / "official"
        / "demo"
        / "sha256_3c22b6b13e68abba0238eba778762eef14136ac61f55a1a59cce8a14e8a8e231"
    )
    text = format_suite_recap(
        {
            "suite_run_id": "ca096a6f",
            "dataset_id": "official/demo",
            "dataset_version": "0.1.0",
            "exit_code": 0,
            "counts": {"pass": 2, "fail": 0, "error": 0, "skipped": 0},
            "summary_path": str(cache_root / "summary.json"),
        },
        dataset_root=cache_root,
    )
    assert "ageval view official/demo@0.1.0" in text
    assert "ageval results upload-suite official/demo@0.1.0 --suite-run ca096a6f" in text
    next_block = text.split("next     ", 1)[-1]
    assert "sha256_3c22" not in next_block
