"""Default ``evaluation_runtime``: run the task evaluator inside the box."""

from __future__ import annotations

from typing import Any


class DefaultEvaluationRuntime:
    """Today's in-box ``evaluator.py`` via ``host.exec``. Returns raw; does not bind."""

    async def evaluate(self, ctx: Any) -> dict[str, Any]:
        from ageval.evaluation.package_evaluator import evaluate_in_box

        return await evaluate_in_box(ctx)


def build_evaluation_runtime(
    *, options: dict[str, Any] | None = None, **_kwargs: Any
) -> DefaultEvaluationRuntime:
    del options
    return DefaultEvaluationRuntime()
