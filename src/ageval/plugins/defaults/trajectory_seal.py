"""Default ``trajectory_seal``: write engine-authored layer C ``trajectory.jsonl``."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DefaultTrajectorySeal:
    """Today's ``write_attempt_trajectory``. Observational — never PASS."""

    def seal(self, ctx: Any, turns: list[list[dict[str, Any]]]) -> Path:
        from ageval.evidence.trajectory import write_attempt_trajectory

        return write_attempt_trajectory(
            ctx.evidence.root,
            turns,
            redaction_sentinels=ctx.evidence.sentinels,
        )


def build_trajectory_seal(
    *, options: dict[str, Any] | None = None, **_kwargs: Any
) -> DefaultTrajectorySeal:
    del options
    return DefaultTrajectorySeal()
