"""Built-in executor capability matrix.

Spec 19: coding-agent surface is ``acp`` only; ``openai-http`` remains api-client.
Private vendor CLI kinds are not first-class.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

ToolsCap = Literal["native", "adapter-loop", "unsupported"]
StructuredCap = Literal["native", "validated-text", "unsupported"]
SessionCap = Literal["new-only", "resume-within-attempt", "unsupported"]
StreamCap = Literal["native-events", "synthetic-lifecycle"]
ExecutionMode = Literal["cli-process", "api-client", "acp-stdio"]


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    kind: str
    tools: ToolsCap
    structured_output: StructuredCap
    session: SessionCap
    stream: StreamCap
    execution_mode: ExecutionMode
    credential_env_names: tuple[str, ...]
    binary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


BUILTIN_CAPABILITIES: Final[dict[str, ExecutorCapabilities]] = {
    "acp": ExecutorCapabilities(
        kind="acp",
        tools="native",
        structured_output="validated-text",
        session="new-only",
        stream="native-events",
        execution_mode="acp-stdio",
        # Entry-specific credential allowlists live on AcpEntryDescriptor.
        credential_env_names=(),
        binary="",
    ),
    "openai-http": ExecutorCapabilities(
        kind="openai-http",
        tools="unsupported",
        structured_output="validated-text",
        session="unsupported",
        stream="synthetic-lifecycle",
        execution_mode="api-client",
        credential_env_names=("OPENAI_API_KEY",),
        binary="",
    ),
}


def get_capabilities(kind: str) -> ExecutorCapabilities | None:
    return BUILTIN_CAPABILITIES.get(kind)


def required_kinds_for_v014() -> frozenset[str]:
    """Historical name: coding-agent surface is now ACP."""
    return frozenset({"acp"})


def residual_kinds() -> frozenset[str]:
    return frozenset()
