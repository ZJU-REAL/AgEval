"""Host inventory for agent executor kinds.

Separates product surface (which adapters BORA ships) from host readiness
(whether CLI binaries resolve on PATH). CLI only prints the result.

Spec 19: ACP rows report engine_ready × acp_entry_ready and readiness enum.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from typing import Any

from bora.adapters.acp_registry import list_entry_ids, load_acp_entries, readiness_for
from bora.adapters.agent_registry import discover_executor_kinds
from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES, get_capabilities

# kind → PATH names to try (first hit wins). Empty = no host CLI required.
_BINARY_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "acp": (),  # readiness is per-entry, not a single binary
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

    if mode == "api-client" or mode == "acp-stdio" or not candidates:
        binary_on_path: bool | None = None
        # ACP kind host_ready is true only when at least one entry is ready.
        if mode == "acp-stdio":
            host_ready = False
            binary_name = None
        else:
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


def describe_acp_entry(
    entry_id: str,
    *,
    which: WhichFn | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """One ACP entry inventory row (Spec 19 readiness enum)."""
    entries = load_acp_entries()
    desc = entries[entry_id]
    ready = readiness_for(desc, which=which)
    row: dict[str, Any] = {
        "kind": "acp",
        "entry_id": desc.entry_id,
        "execution_mode": "acp-stdio",
        "integration_mode": desc.integration_mode,
        "engine_command": desc.engine_command,
        "acp_command": list(desc.acp_command),
        "acp_version": desc.acp_version,
        "engine_version": desc.engine_version,
        "engine_ready": ready["engine_ready"],
        "acp_entry_ready": ready["acp_entry_ready"],
        "readiness": ready["readiness"],
        "host_ready": ready["readiness"] == "ready",
        # PATH absolute locations only in verbose (not lock fields).
        "binary": ready.get("acp_binary"),
        "binary_on_path": ready["acp_entry_ready"],
        "binary_path": ready.get("acp_path") if verbose else None,
    }
    if verbose:
        row["credential_env_names"] = list(desc.credential_env_names)
        row["install_command"] = desc.install_command
        row["descriptor_digest"] = desc.descriptor_digest
        row["model_binding"] = desc.model_binding
        row["engine_path"] = ready.get("engine_path")
        row["tools"] = "native"
        row["structured_output"] = "validated-text"
        row["session"] = "new-only"
        row["stream"] = "native-events"
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
    - ``executors``: per-kind rows (legacy kinds)
    - ``acp_entries``: per ACP entry readiness rows (Spec 19)
    """
    supported = supported_executor_kinds()
    rows = [describe_executor(k, which=which, verbose=verbose) for k in supported]
    acp_rows = [
        describe_acp_entry(eid, which=which, verbose=verbose) for eid in list_entry_ids()
    ]
    # Reflect aggregate ACP readiness on the acp kind row.
    for row in rows:
        if row.get("kind") == "acp":
            row["host_ready"] = any(r.get("host_ready") for r in acp_rows)
            row["acp_entries_ready"] = sorted(
                r["entry_id"] for r in acp_rows if r.get("host_ready")
            )
    return {
        "supported": supported,
        "host_ready": sorted(r["kind"] for r in rows if r.get("host_ready")),
        "missing_binary": sorted(
            r["kind"] for r in rows if r.get("binary_on_path") is False
        ),
        "executors": rows,
        "acp_entries": acp_rows,
    }
