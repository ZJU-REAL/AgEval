"""NVIDIA nooa agents for multiagent env diagnostics (real LLM via executor)."""

from __future__ import annotations

from nooa import Agent
from pydantic import BaseModel, Field


class SpecialistFinding(BaseModel):
    specialist: str
    active: bool
    label: str | None = None
    evidence: str = ""


class PlannerDecision(BaseModel):
    follow_up_sql: str | None = None
    rationale: str = ""


class ReducerOutput(BaseModel):
    predicted_labels: list[str] = Field(default_factory=list)
    supporting_specialists: list[str] = Field(default_factory=list)


class SpecialistAgent(Agent):
    """You are one SQL diagnostics specialist.

    Decide whether your specialty is active from the ROWS / evidence in the prompt.
    Return SpecialistFinding. Use the specialist role name from the prompt.
    Only mark active when the evidence clearly supports that specialty.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> SpecialistFinding:
        """Analyze evidence for this specialist role.

        {prompt}
        """
        ...


class PlannerAgent(Agent):
    """You are the planner for SQL diagnostics.

    Optionally propose one follow-up SQL query, or null when seed evidence is enough.
    Return PlannerDecision.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> PlannerDecision:
        """Decide follow-up SQL if needed.

        {prompt}
        """
        ...


class ReducerAgent(Agent):
    """You are the reducer for SQL diagnostics.

    From specialist findings, return exactly three unique predicted_labels
    chosen only from the allowed label set in the prompt.
    Prefer labels whose specialists reported active=true with supporting evidence.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> ReducerOutput:
        """Reduce findings to three labels.

        {prompt}
        """
        ...
