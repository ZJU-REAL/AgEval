"""Thin task evaluator — scoring in Dataset shared/lib (#65)."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from evaluator_core import evaluate as _evaluate
_TASK = Path(__file__).resolve().parent
UPSTREAM_TASK_ID = "6"
def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    return _evaluate(inputs, task_dir=_TASK, upstream_task_id=UPSTREAM_TASK_ID)
