"""Built-in executor capability matrix (v0.14).

Declared capabilities enter lock snapshots; mismatches fail closed before
Attempt external effects. No benchmark/task branching.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

ToolsCap = Literal["native", "adapter-loop", "unsupported"]
StructuredCap = Literal["native", "validated-text", "unsupported"]
SessionCap = Literal["new-only", "resume-within-attempt", "unsupported"]
StreamCap = Literal["native-events", "synthetic-lifecycle"]
ExecutionMode = Literal["cli-process", "api-client"]


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    kind: str
    tools: ToolsCap
    structured_output: StructuredCap
    session: SessionCap
    stream: StreamCap
    execution_mode: ExecutionMode
    # Host-native credential env names (locators only — never values).
    credential_env_names: tuple[str, ...]
    binary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Frozen from Phase 0 host CLI probes (2026-08-03).
BUILTIN_CAPABILITIES: Final[dict[str, ExecutorCapabilities]] = {
    "codex": ExecutorCapabilities(
        kind="codex",
        tools="native",
        structured_output="validated-text",
        session="new-only",
        stream="native-events",
        execution_mode="cli-process",
        credential_env_names=(),  # host login / CODEX_* via existing session
        binary="codex",
    ),
    "pi": ExecutorCapabilities(
        kind="pi",
        tools="native",
        structured_output="validated-text",
        session="new-only",
        stream="native-events",
        execution_mode="cli-process",
        # From `pi --help` Environment Variables; Zhipu coding plan aliases.
        credential_env_names=(
            "ZAI_API_KEY",
            "ZAI_CODING_CN_API_KEY",
            "ZHIPU_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "XAI_API_KEY",
        ),
        binary="pi",
    ),
    "opencode": ExecutorCapabilities(
        kind="opencode",
        tools="native",
        structured_output="validated-text",
        session="new-only",
        stream="native-events",
        execution_mode="cli-process",
        credential_env_names=(
            "ZHIPU_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "OPENCODE_API_KEY",
            "XAI_API_KEY",
        ),
        binary="opencode",
    ),
    # Residual: registered only when executable is on PATH (Phase 1 optional).
    "claude-code": ExecutorCapabilities(
        kind="claude-code",
        tools="native",
        structured_output="validated-text",
        session="new-only",
        stream="synthetic-lifecycle",
        execution_mode="cli-process",
        credential_env_names=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        binary="claude",
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
    return frozenset({"codex", "pi", "opencode"})


def residual_kinds() -> frozenset[str]:
    return frozenset({"claude-code"})
