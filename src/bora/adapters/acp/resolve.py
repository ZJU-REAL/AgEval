"""Factory for AcpExecutor from entry id."""

from __future__ import annotations

from typing import Any

from bora.adapters.acp.executor import AcpExecutor


def resolve_acp_executor(
    *,
    entry_id: str,
    model: str,
    reasoning_effort: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> AcpExecutor:
    return AcpExecutor(
        entry_id=entry_id,
        model=model,
        reasoning_effort=reasoning_effort,
        base_url=base_url,
        api_key_env=api_key,
    )
