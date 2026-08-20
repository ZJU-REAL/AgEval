"""Run the task's ``evaluator.py`` inside the same box, after gold is uploaded.

Same box, later in time: the evaluator sees ``/attempt/evaluation`` (gold) and
``/attempt/artifacts`` (what the task published), which the Agent never could.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.config.model import thaw
from ageval.environments.protocol import EVALUATION_PATH

_RUNNER_NAME = "_ageval_evaluator_runner.py"
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

    request = {
        "entrypoint": entrypoint,
        "module_file": module_file,
        "inputs": refs.get("evaluation_inputs") or [],
        "parameters": thaw(ctx.lock.parameters),
    }
    # argv is relative to the mapped cwd: an in-box absolute path would be a
    # literal string to a local box, which has no ``/attempt`` on disk.
    #
    # Local boxes share this interpreter's filesystem, so the evaluator process
    # gets the same import contract as ``run.py``: dataset root then task dir
    # (``from shared.lib…``). Docker/e2b/ssh must bake or COPY ``shared/``.
    exec_env = None
    if getattr(ctx.host, "kind", None) == "local":
        exec_env = {
            "PYTHONPATH": os.pathsep.join(
                [str(ctx.dataset_root.resolve()), str(ctx.task_root.resolve())]
            )
        }
    result = await ctx.host.exec(
        [*ctx.host.python_command, _RUNNER_NAME, json.dumps(request)],
        cwd=_BOX_EVALUATOR_DIR,
        env=exec_env,
        timeout_sec=ctx.remaining_seconds(),
    )
    ctx.record_fact("evaluator_exec", {"exit_code": result.exit_code})
    if result.exit_code != 0:
        raise RuntimeError(
            f"evaluator exited {result.exit_code}: {(result.stderr or result.stdout)[-500:]}"
        )
    return _read_verdict(ctx, result.stdout)


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
