"""pass@k / pass^k unit tests (#47)."""

from __future__ import annotations

import pytest

from bora.application.suite.suite_metrics import (
    aggregate_k_metrics,
    default_k_values,
    pass_at_k,
    pass_power_k,
)


def test_pass_at_k_basic() -> None:
    # n=k=1, c=1 → 1.0; c=0 → 0.0
    assert pass_at_k(n=1, c=1, k=1) == pytest.approx(1.0)
    assert pass_at_k(n=1, c=0, k=1) == pytest.approx(0.0)
    # pass@1 = c/n
    assert pass_at_k(n=10, c=3, k=1) == pytest.approx(0.3)
    # incomplete
    assert pass_at_k(n=3, c=2, k=5) is None
    # n=10, c=3, k=5: classic sample 1 - C(7,5)/C(10,5)
    expected = 1.0 - (21 / 252)
    assert pass_at_k(n=10, c=3, k=5) == pytest.approx(expected)


def test_pass_at_k_all_correct() -> None:
    assert pass_at_k(n=5, c=5, k=5) == pytest.approx(1.0)
    assert pass_at_k(n=5, c=5, k=3) == pytest.approx(1.0)


def test_pass_power_k() -> None:
    assert pass_power_k(n=4, c=2, k=2) == pytest.approx(0.25)
    assert pass_power_k(n=4, c=4, k=3) == pytest.approx(1.0)
    assert pass_power_k(n=4, c=0, k=2) == pytest.approx(0.0)
    assert pass_power_k(n=0, c=0, k=1) is None


def test_default_k_values() -> None:
    assert default_k_values(1) == [1]
    assert default_k_values(8) == [1, 2, 4, 5, 8]
    assert default_k_values(10) == [1, 2, 4, 5, 8, 10]
    assert default_k_values(0) == []


def test_aggregate_k_mean_over_tasks() -> None:
    # task a: 2/2 pass; task b: 0/2 pass → pass@1 mean = (1 + 0) / 2 = 0.5
    attempts = [
        {"task_id": "a", "attempt_index": 0, "status": "PASS"},
        {"task_id": "a", "attempt_index": 1, "status": "PASS"},
        {"task_id": "b", "attempt_index": 0, "status": "FAIL"},
        {"task_id": "b", "attempt_index": 1, "status": "FAIL"},
    ]
    m = aggregate_k_metrics(attempts, task_ids=["a", "b"], n_attempts=2)
    assert m["pass_at_k"]["1"]["value"] == pytest.approx(0.5)
    assert m["pass_at_k"]["2"]["value"] == pytest.approx(0.5)  # a→1, b→0
    assert m["pass_power_k"]["2"]["value"] == pytest.approx(0.5)  # a:(1)^2=1, b:0 → mean 0.5
    assert m["n_pass"] == 1  # rolled task status: a PASS, b FAIL
    assert m["n_fail"] == 1


def test_incomplete_task_excluded_from_mean() -> None:
    attempts = [
        {"task_id": "a", "attempt_index": 0, "status": "PASS"},
        {"task_id": "a", "attempt_index": 1, "status": "PASS"},
        # b only 1 sample — incomplete for k=2
        {"task_id": "b", "attempt_index": 0, "status": "PASS"},
    ]
    m = aggregate_k_metrics(attempts, task_ids=["a", "b"], n_attempts=2, k_values=[1, 2])
    assert m["pass_at_k"]["2"]["n_tasks"] == 1
    assert m["pass_at_k"]["2"]["incomplete_tasks"] == 1
    assert m["pass_at_k"]["2"]["value"] == pytest.approx(1.0)
    assert m["pass_at_k"]["1"]["n_tasks"] == 2
