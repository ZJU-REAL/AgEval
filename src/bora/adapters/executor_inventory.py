"""Host inventory for agent executor kinds.

Separates product surface (which adapters BORA ships) from host readiness
(whether CLI binaries resolve on PATH). CLI only prints the result.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from typing import Any

from bora.adapters.agent_registry import discover_executor_kinds
from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES, get_capabilities

# kind → PATH names to try (first hit wins). Empty = no host CLI required.
_BINARY_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "codex": ("codex",),
    "pi": ("pi",),
    "opencode": ("opencode",),
    "claude-code": ("claude", "claude-code"),
    "openai-http": (),
    "openai": (),
    "openai_responses": (),
}

# Factory aliases without their own capability row.
_API_ALIASES: frozenset[str] = frozenset({"openai", "openai_responses"})

WhichFn = Callable[[str], str | None]


def supported_executor_kinds() -> list[str]:
    """Kinds valid for ``agent_profiles[].executor`` on this install."""
    return sorted(
        set(BUILTIN_CAPABILITIES)
        | set(discover_executor_kinds())
        | set(_API_ALIASES)
    )


def probe_binary(
    candidates: tuple[str, ...],
    *,
    which: WhichFn | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(binary_name, absolute_path)`` for the first PATH hit.

    Uses :func:`shutil.which`, which is cross-platform (POSIX + Windows,
    including ``PATHEXT`` on Windows so ``codex`` resolves to ``codex.exe``).
    """
    which_fn = which or shutil.which
    for name in candidates:
        hit = which_fn(name)
        if hit:
            return name, hit
    return (candidates[0] if candidates else None), None


def binary_candidates_for(kind: str) -> tuple[str, ...]:
    """PATH names to probe for ``kind``."""
    if kind in _BINARY_CANDIDATES:
        return _BINARY_CANDIDATES[kind]
    caps = get_capabilities(kind)
    if caps is not None and caps.binary:
        return (caps.binary,)
    return ()


def describe_executor(
    kind: str,
    *,
    which: WhichFn | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """One inventory row: support metadata + host binary probe."""
    caps = get_capabilities(kind)
    if caps is not None:
        mode = caps.execution_mode
    elif kind in _API_ALIASES:
        mode = "api-client"
    else:
        mode = "unknown"

    candidates = binary_candidates_for(kind)
    binary_name, binary_path = probe_binary(candidates, which=which)

    if mode == "api-client" or not candidates:
        binary_on_path: bool | None = None
        host_ready = True
        # Prefer empty name over a fake CLI for pure HTTP adapters.
        if not candidates:
            binary_name = None
    else:
        binary_on_path = binary_path is not None
        host_ready = binary_on_path

    row: dict[str, Any] = {
        "kind": kind,
        "execution_mode": mode,
        "binary": binary_name,
        "binary_on_path": binary_on_path,
        "binary_path": binary_path,
        "host_ready": host_ready,
    }
    if verbose:
        if caps is not None:
            row["credential_env_names"] = list(caps.credential_env_names)
            row["tools"] = caps.tools
            row["structured_output"] = caps.structured_output
            row["session"] = caps.session
            row["stream"] = caps.stream
        else:
            row["credential_env_names"] = []
    return row


def build_executor_inventory(
    *,
    which: WhichFn | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Full inventory for ``bora executors`` (JSON-serializable).

    Fields:
    - ``supported``: adapters this install provides
    - ``host_ready``: kinds ready on this host (CLI on PATH or api-client)
    - ``missing_binary``: CLI kinds whose binary is not on PATH
    - ``executors``: per-kind rows
    """
    supported = supported_executor_kinds()
    rows = [describe_executor(k, which=which, verbose=verbose) for k in supported]
    return {
        "supported": supported,
        "host_ready": sorted(r["kind"] for r in rows if r.get("host_ready")),
        "missing_binary": sorted(
            r["kind"] for r in rows if r.get("binary_on_path") is False
        ),
        "executors": rows,
    }
