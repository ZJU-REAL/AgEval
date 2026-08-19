"""Run the task's ``evaluator.py`` inside the same box, after gold is uploaded.

Same box, later in time: the evaluator sees ``/attempt/evaluation`` (gold) and
``/attempt/artifacts`` (what the task published), which the Agent never could.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.config.model import thaw
from ageval.environments.protocol import ARTIFACTS_PATH, EVALUATION_PATH

_RUNNER_NAME = "_ageval_evaluator_runner.py"
_RESULT_NAME = "evaluation.json"
_BOX_EVALUATOR_DIR = f"{EVALUATION_PATH}/_evaluator"


async def evaluate_in_box(ctx: AttemptCtx) -> dict[str, Any]:
    """Upload evaluator + artifacts, exec it in the box, read back the verdict."""
    refs = thaw(ctx.lock.resolved_references)
    entrypoint = str(refs.get("evaluation_entrypoint") or "evaluator:evaluate")
    module_file = str(refs.get("evaluation_module_file") or "evaluator.py")

    evaluator_src = ctx.task_root / module_file
    if not evaluator_src.is_file():
        raise FileNotFoundError(f"evaluator module missing: {module_file}")

    await ctx.host.upload(evaluator_src, f"{_BOX_EVALUATOR_DIR}/{module_file}")
    await ctx.host.upload(_runner_source_path(), f"{_BOX_EVALUATOR_DIR}/{_RUNNER_NAME}")
    await _upload_published_artifacts(ctx)

    request = {
        "entrypoint": entrypoint,
        "module_file": module_file,
        "artifacts_dir": ARTIFACTS_PATH,
        "evaluation_dir": EVALUATION_PATH,
        "artifacts": _artifact_paths(ctx),
        "inputs": refs.get("evaluation_inputs") or [],
        "parameters": thaw(ctx.lock.parameters),
        "result_path": f"{ARTIFACTS_PATH}/{_RESULT_NAME}",
    }
    result = await ctx.host.exec(
        ["python3", f"{_BOX_EVALUATOR_DIR}/{_RUNNER_NAME}", json.dumps(request)],
        cwd=ARTIFACTS_PATH,
        timeout_sec=ctx.remaining_seconds(),
    )
    ctx.record_fact("evaluator_exec", {"exit_code": result.exit_code})
    if result.exit_code != 0:
        raise RuntimeError(
            f"evaluator exited {result.exit_code}: {(result.stderr or result.stdout)[-500:]}"
        )
    return _read_verdict(ctx, result.stdout)


async def _upload_published_artifacts(ctx: AttemptCtx) -> None:
    """Move host-side published artifacts into the box before judging."""
    staged = ctx.evidence.path("task-artifacts")
    if staged.is_dir() and any(staged.iterdir()):
        await ctx.host.upload(staged, ARTIFACTS_PATH)


def _artifact_paths(ctx: AttemptCtx) -> dict[str, str]:
    """Declared artifact id → in-box path, for what the task actually published."""
    staged = ctx.evidence.path("task-artifacts")
    if not staged.is_dir():
        return {}
    return {
        item.stem: f"{ARTIFACTS_PATH}/{item.name}"
        for item in sorted(staged.iterdir())
        if item.is_file()
    }


def _read_verdict(ctx: AttemptCtx, stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise RuntimeError("evaluator produced no verdict document")
    try:
        doc = json.loads(text.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"evaluator verdict is not JSON: {text[-300:]}") from exc
    if not isinstance(doc, dict):
        raise RuntimeError("evaluator verdict must be a JSON object")
    ctx.evidence.write_evaluation("evaluator_raw", doc)
    return doc


def _runner_source_path() -> Path:
    return Path(__file__).with_name("box_runner.py")
