"""Stable Agent outlet contract shared by ACP and openai-http executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AgentResult:
    model: str
    text: str
    structured: dict[str, object] | None
    ok: bool
    error: str | None = None
    stderr: str = ""
    events: tuple[dict[str, Any], ...] = ()
    source_refs: tuple[dict[str, str], ...] = ()
    usage: dict[str, Any] | None = None
    # ACP / executor metadata (lock-safe, no secrets).
    metadata: dict[str, Any] | None = None


class AgentExecutor(Protocol):
    kind: str

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult: ...


def parse_validated_text_structured(text: str) -> dict[str, object] | None:
    """Return structured only when trimmed final text is a complete JSON object.

    No substring/reverse-scan/regex salvage (Spec 19 decision 5).
    """
    import json

    trimmed = text.strip()
    if not trimmed or not trimmed.startswith("{") or not trimmed.endswith("}"):
        return None
    try:
        val = json.loads(trimmed)
    except json.JSONDecodeError:
        return None
    if isinstance(val, dict):
        return val  # type: ignore[return-value]
    return None
