"""L1 placement helpers (no private vendor CLI scrape).

Production ACP path uses parent ``AcpExecutor`` + ``docker exec -i`` attach.
Opaque target ids live here for Provider ledger; fail-closed generation probes
remain for unit tests without reintroducing stdout parsers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from bora.adapters.agent_contract import AgentResult
from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget


def new_opaque_target_id() -> str:
    return f"tgt_{uuid.uuid4().hex[:16]}"


def effective_run_gid(actor: ActorPhysicalBinding) -> int:
    """Primary GID for docker exec: shared GID when shared_write is granted."""
    if actor.shared_gid is not None and actor.shared_write:
        return int(actor.shared_gid)
    return int(actor.gid)


@dataclass
class ContainerCLIExecutor:
    """Fail-closed target/generation probe only — private CLI scrape removed.

    Ready targets refuse invoke with ``migrated_to_acp``; use AcpExecutor.
    """

    kind: str
    model: str
    container_id: str
    actor: ActorPhysicalBinding
    target: ExecutionTarget
    env: dict[str, str]
    workdir: str = "/attempt/workspace"
    api_key_env: str | None = None
    base_url: str | None = None
    host_fallback_counter: list[int] | None = None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 300.0,
        collect_dir: str | Path | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
        workdir: str | None = None,
    ) -> AgentResult:
        del prompt, timeout, collect_dir, redaction_sentinels, workdir
        from bora.runtime.offline import is_offline_agent

        if is_offline_agent():
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "skipped",
                        "reason": "offline_forced",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                    },
                ),
            )
        if self.target.state != "ready" or not self.container_id:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="target_dead",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "target_dead",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                        "target_id": self.target.target_id,
                        "generation": self.actor.generation,
                    },
                ),
            )
        if self.target.generation != self.actor.generation:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="generation_mismatch",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "generation_mismatch",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                        "target_id": self.target.target_id,
                        "session_generation": self.actor.generation,
                        "target_generation": self.target.generation,
                    },
                ),
            )
        return AgentResult(
            model=self.model,
            text="",
            structured=None,
            ok=False,
            error="migrated_to_acp",
            events=(
                {
                    "type": "lifecycle",
                    "phase": "failed",
                    "reason": "migrated_to_acp",
                    "source": "container_executor",
                    "execution_location": "attempt-container",
                },
            ),
        )
