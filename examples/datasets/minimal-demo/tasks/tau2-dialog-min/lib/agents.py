"""NVIDIA nooa agents for tau2 retail dialog (real LLM via executor wiring)."""

from __future__ import annotations

from nooa import Agent
from pydantic import BaseModel, Field


class CustomerMessage(BaseModel):
    message: str


class ToolAction(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


class UserSimAgent(Agent):
    """You generate ONE synthetic retail-customer support message.

    Embed the email and known_order_id from the private facts exactly.
    Natural tone. No tools. No system meta. Return only CustomerMessage.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> CustomerMessage:
        """Produce the customer message for this fixture prompt.

        {prompt}
        """
        ...


class ServiceAgent(Agent):
    """You are a retail support service agent driving a fixed tool workflow.

    Available tools (call exactly one per turn as ToolAction JSON):
    - find_customer(email)
    - get_order(order_id)
    - get_product(item_id)
    - request_exchange(order_id, from_item_ids, to_item_ids)
    - done(note)

    Use only identifiers present in the customer message / tool observations.
    Prefer the headphones black exchange path when facts support it.
    Never invent emails or order ids. Return exactly one ToolAction per turn.
    """

    async def run(self, prompt: str, workdir: str | None = None) -> ToolAction:
        """Choose the next tool action given the dialog state.

        {prompt}
        """
        ...
