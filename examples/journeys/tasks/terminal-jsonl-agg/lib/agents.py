"""NVIDIA nooa agents for terminal-jsonl-agg (real LLM via executor wiring)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nooa import Agent
from pydantic import BaseModel, Field


class Aggregates(BaseModel):
    """Workspace aggregates.json payload."""

    top_5_users_by_amount: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    top_5_tags_by_count: dict[str, dict[str, int]] = Field(default_factory=dict)


class JsonlAggAgent(Agent):
    """You aggregate JSONL commerce records for an automated evaluator.

    Read every ``records_*.jsonl`` under the given workdir. Compute:
    - top 5 users by total_amount desc, then total_items desc, then name asc
    - top 5 tags by count desc, then name asc

    Write ``aggregates.json`` in workdir and return the same object.
    Amounts are rounded to 2 decimals. Do not invent rows.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> Aggregates:
        """Solve the aggregation task described below and return Aggregates.

        Task / instruction:
        {prompt}

        Working directory (read records_*.jsonl here; write aggregates.json here):
        {workdir}
        """
        ...


def write_aggregates_fallback(workdir: str | Path, data: dict[str, Any]) -> Path:
    """Optional host helper — executor does not require this."""
    root = Path(workdir).expanduser().resolve(strict=False)
    out = root / "aggregates.json"
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
