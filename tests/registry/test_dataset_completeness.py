"""Draft slot constants and suite completeness predicate."""

from __future__ import annotations

from services.registry.dataset import (
    DRAFT_VERSION,
    is_draft_version,
    suite_is_complete,
    task_has_result,
    task_ids_from_file_paths,
    task_set_digest,
)


def test_draft_version_reserved() -> None:
    assert is_draft_version("draft")
    assert is_draft_version("DRAFT")
    assert not is_draft_version("0.1.0")
    assert DRAFT_VERSION == "draft"


def test_task_ids_from_archive_paths() -> None:
    ids = task_ids_from_file_paths(
        [
            "ageval.yaml",
            "tasks/alpha/task.yaml",
            "tasks/alpha/run.py",
            "tasks/beta/task.yaml",
            "README.md",
        ]
    )
    assert ids == frozenset({"alpha", "beta"})


def test_fail_counts_as_result() -> None:
    assert task_has_result({"task_id": "a", "status": "FAIL", "score": 0.0})
    assert task_has_result({"task_id": "a", "status": "ERROR"})
    assert not task_has_result({"task_id": "a"})
    assert not task_has_result({"status": "PASS"})


def test_complete_requires_every_bound_task() -> None:
    bound = {"alpha", "beta"}
    assert suite_is_complete(
        bound_task_ids=bound,
        task_refs=[
            {"task_id": "alpha", "status": "PASS", "score": 1.0},
            {"task_id": "beta", "status": "FAIL", "score": 0.0},
        ],
    )
    assert not suite_is_complete(
        bound_task_ids=bound,
        task_refs=[{"task_id": "alpha", "status": "PASS", "score": 1.0}],
    )


def test_n_attempts_mismatch_does_not_disqualify() -> None:
    assert suite_is_complete(
        bound_task_ids={"a", "b"},
        task_refs=[
            {"task_id": "a", "status": "PASS", "n": 3, "c": 2},
            {"task_id": "b", "status": "FAIL", "n": 1, "c": 0},
        ],
    )


def test_empty_bound_set_is_incomplete() -> None:
    assert not suite_is_complete(bound_task_ids=[], task_refs=[])


def test_task_set_digest_is_stable() -> None:
    assert task_set_digest(["b", "a"]) == task_set_digest(["a", "b"])
    assert task_set_digest(["a"]) != task_set_digest(["a", "b"])
