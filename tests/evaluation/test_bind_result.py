"""Verdict bind is fail-closed on unknown status strings."""

from ageval.evaluation.bind import bind_result


def test_bind_result_accepts_pass_fail_error() -> None:
    for status in ("PASS", "FAIL", "ERROR"):
        result = bind_result(
            evaluator_raw={"status": status, "score": 1},
            kind="local",
            evidence_path="/tmp/evidence",
        )
        assert result.status == status


def test_bind_result_rejects_lowercase_and_unknown() -> None:
    for status in ("pass", "PASSED", "ok", "", None):
        raw = {"status": status} if status is not None else {}
        result = bind_result(
            evaluator_raw=raw,
            kind="local",
            evidence_path="/tmp/evidence",
        )
        assert result.status == "ERROR"
        assert result.error_phase == "evaluate"


def test_bind_result_missing_raw_is_error() -> None:
    result = bind_result(
        evaluator_raw=None,
        kind="local",
        evidence_path="/tmp/evidence",
    )
    assert result.status == "ERROR"
    assert result.error_phase == "evaluate"


def test_bind_result_phase_failure_wins() -> None:
    result = bind_result(
        evaluator_raw={"status": "PASS", "score": 1},
        kind="local",
        evidence_path="/tmp/evidence",
        error_phase="run",
    )
    assert result.status == "ERROR"
    assert result.error_phase == "run"
    assert result.score is None
