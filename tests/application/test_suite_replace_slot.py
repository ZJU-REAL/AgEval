"""Named-slot replace on a finished suite: new Attempt + previous[] history."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ageval.application.suite.suite_metrics import (
    extend_slot_previous,
    previous_from_attempts,
    task_refs_for_summary,
)
from ageval.application.suite.suite_run import (
    execute_suite_run,
    plan_suite_run,
    request_suite_cancel,
    suite_dir_for,
)
from ageval.config.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "datasets" / "suite-min"


def _runner(status: str = "PASS", score: float | None = 1.0, *, prefix: str = "cur"):
    n = {"n": 0}

    async def run(root, task_id, *, overrides=None, profiles_path=None, **kwargs):  # noqa: ANN001
        n["n"] += 1
        run_id = f"sha256_dead_run_{prefix}_{task_id}_{n['n']}"
        abs_run = Path(root) / ".ageval" / "runs" / run_id
        abs_run.mkdir(parents=True, exist_ok=True)
        st = status
        sc = score
        code = 0 if st == "PASS" else (1 if st == "FAIL" else 2)
        result = SimpleNamespace(status=st, score=sc, evidence_path=str(abs_run), logs=str(abs_run))
        return code, result, {"digest": f"sha256:{run_id}", "run_dir": str(abs_run)}

    run.calls = n  # type: ignore[attr-defined]
    return run


def test_extend_previous_oldest_to_newest() -> None:
    first = {
        "task_id": "alpha",
        "attempt_index": 0,
        "run_id": "old",
        "status": "ERROR",
        "score": None,
        "previous": [
            {
                "run_id": "older",
                "status": "FAIL",
                "score": 0.0,
                "attempt_index": 0,
                "replaced_at": "t0",
            }
        ],
    }
    chain = extend_slot_previous(first, replaced_at="t1")
    assert [e["run_id"] for e in chain] == ["older", "old"]
    assert chain[-1]["replaced_at"] == "t1"
    assert chain[-1]["status"] == "ERROR"


def test_task_refs_copy_previous_from_attempts() -> None:
    refs = task_refs_for_summary(
        [{"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": "new"}],
        attempts=[
            {
                "task_id": "alpha",
                "attempt_index": 0,
                "run_id": "new",
                "status": "PASS",
                "score": 1.0,
                "previous": [
                    {
                        "run_id": "old",
                        "status": "ERROR",
                        "score": None,
                        "attempt_index": 0,
                        "replaced_at": "t",
                    }
                ],
            }
        ],
    )
    assert refs[0]["run_id"] == "new"
    assert refs[0]["previous"][0]["run_id"] == "old"
    assert previous_from_attempts([]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status,score", [("ERROR", None), ("FAIL", 0.0), ("PASS", 1.0)])
async def test_replace_slot_reruns_finished_and_keeps_history(
    status: str, score: float | None
) -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=1)
    first = await execute_suite_run(plan, run_fn=_runner(status, score, prefix="old"))
    old_id = first["attempts"][0]["run_id"]
    assert first["attempts"][0]["status"] == status
    old_dir = Path(plan.dataset_root) / ".ageval" / "runs" / old_id
    assert old_dir.is_dir()

    plan2 = plan_suite_run(SUITE, task_id="alpha", n_attempts=1, suite_run_id=first["suite_run_id"])
    second = await execute_suite_run(
        plan2,
        run_fn=_runner("PASS", 1.0, prefix="new"),
        resume=True,
        replace_slots={("alpha", 0)},
    )
    assert second["resumed"] is True
    assert second["amended"] is True
    assert second["new_attempts"] == 1
    assert len(second["attempts"]) == 1
    cur = second["attempts"][0]
    assert cur["run_id"] != old_id
    assert cur["status"] == "PASS"
    assert cur["previous"][0]["run_id"] == old_id
    assert cur["previous"][0]["status"] == status
    assert old_dir.is_dir()
    refs = {r["task_id"]: r for r in second["task_refs"]}
    assert refs["alpha"]["run_id"] == cur["run_id"]
    assert refs["alpha"]["previous"][0]["run_id"] == old_id
    assert second["metrics"]["n_pass"] == 1
    disk = json.loads(Path(second["summary_path"]).read_text(encoding="utf-8"))
    assert disk["amended"] is True
    assert disk["attempts"][0]["previous"][0]["run_id"] == old_id


@pytest.mark.asyncio
async def test_resume_without_replace_skips_finished_error() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=1)
    first = await execute_suite_run(plan, run_fn=_runner("ERROR", None, prefix="err"))
    old_id = first["attempts"][0]["run_id"]
    plan2 = plan_suite_run(SUITE, task_id="alpha", n_attempts=1, suite_run_id=first["suite_run_id"])
    runner = _runner("PASS", 1.0, prefix="skip")
    second = await execute_suite_run(plan2, run_fn=runner, resume=True)
    assert runner.calls["n"] == 0  # type: ignore[attr-defined]
    assert second["new_attempts"] == 0
    assert second["attempts"][0]["run_id"] == old_id
    assert "amended" not in second


@pytest.mark.asyncio
async def test_replace_one_always_k_index_leaves_siblings() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=3, max_concurrent_tasks=1)
    first = await execute_suite_run(plan, run_fn=_runner("FAIL", 0.0, prefix="k"))
    by_idx = {a["attempt_index"]: a["run_id"] for a in first["attempts"]}
    assert first["metrics"]["n_pass"] == 0

    plan2 = plan_suite_run(
        SUITE,
        task_id="alpha",
        n_attempts=3,
        suite_run_id=first["suite_run_id"],
    )
    second = await execute_suite_run(
        plan2,
        run_fn=_runner("PASS", 1.0, prefix="rep"),
        resume=True,
        replace_slots={("alpha", 1)},
    )
    cur = {a["attempt_index"]: a for a in second["attempts"]}
    assert set(cur) == {0, 1, 2}
    assert cur[0]["run_id"] == by_idx[0]
    assert cur[2]["run_id"] == by_idx[2]
    assert cur[1]["run_id"] != by_idx[1]
    assert cur[1]["status"] == "PASS"
    assert "previous" not in cur[0]
    assert cur[1]["previous"][0]["run_id"] == by_idx[1]
    assert second["metrics"]["n_pass"] == 1
    # pass@1 uses current 3 samples (1 pass).
    assert second["metrics"]["pass_at_k"]["1"]["value"] == pytest.approx(1 / 3)
    refs = {r["task_id"]: r for r in second["task_refs"]}
    assert refs["alpha"]["attempt_run_ids"] == [
        cur[0]["run_id"],
        cur[1]["run_id"],
        cur[2]["run_id"],
    ]


@pytest.mark.asyncio
async def test_replace_refuses_in_progress_and_missing_slot() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=1)
    first = await execute_suite_run(plan, run_fn=_runner("ERROR", None, prefix="blk"))
    suite_id = first["suite_run_id"]
    plan2 = plan_suite_run(SUITE, task_id="alpha", n_attempts=1, suite_run_id=suite_id)

    request_suite_cancel(plan.dataset_root, suite_id)
    with pytest.raises(ConfigError, match="in progress"):
        await execute_suite_run(
            plan2,
            run_fn=_runner("PASS", 1.0, prefix="no"),
            resume=True,
            replace_slots={("alpha", 0)},
        )
    (suite_dir_for(plan2) / "cancel.requested").unlink()

    with pytest.raises(ConfigError, match="no finished slot"):
        await execute_suite_run(
            plan2,
            run_fn=_runner("PASS", 1.0, prefix="no"),
            resume=True,
            replace_slots={("alpha", 3)},
        )

    with pytest.raises(ConfigError, match="replace-slot requires"):
        await execute_suite_run(
            plan,
            run_fn=_runner("PASS", 1.0, prefix="no"),
            replace_slots={("alpha", 0)},
        )


@pytest.mark.asyncio
async def test_replace_refuses_fingerprint_mismatch() -> None:
    plan = plan_suite_run(SUITE, task_id="alpha", n_attempts=1)
    first = await execute_suite_run(plan, run_fn=_runner("ERROR", None, prefix="fp"))
    path = Path(first["summary_path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["config_fingerprint"] = "sha256:not-the-real-fingerprint"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    plan2 = plan_suite_run(SUITE, task_id="alpha", n_attempts=1, suite_run_id=first["suite_run_id"])
    with pytest.raises(ConfigError, match="config_fingerprint"):
        await execute_suite_run(
            plan2,
            run_fn=_runner("PASS", 1.0, prefix="no"),
            resume=True,
            replace_slots={("alpha", 0)},
        )
