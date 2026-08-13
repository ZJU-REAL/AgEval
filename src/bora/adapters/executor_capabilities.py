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
# Documented builtins: acp-stdio, api-client, container-worker. Plugins may use others.
ExecutionMode = str


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
    found = BUILTIN_CAPABILITIES.get(kind)
    if found is not None:
        return found
    return _plugin_published_capabilities(kind)


def _plugin_published_capabilities(kind: str) -> ExecutorCapabilities | None:
    """Capabilities published by an installed plugin's describe() / SPI."""
    try:
        from bora.plugins.bootstrap import ensure_bootstrapped
        from bora.plugins.slots import EXECUTOR
    except Exception:  # noqa: BLE001
        return None
    try:
        reg = ensure_bootstrapped()
    except Exception:  # noqa: BLE001
        return None
    rec = reg.get_registration(EXECUTOR, kind)
    if rec is None:
        return None
    desc = _describe_from_provider(rec.impl)
    if desc is None:
        return None
    return ExecutorCapabilities(
        kind=kind,
        tools=str(desc.get("tools") or "unsupported"),  # type: ignore[arg-type]
        structured_output=str(desc.get("structured_output") or "unsupported"),  # type: ignore[arg-type]
        session=str(desc.get("session") or "unsupported"),  # type: ignore[arg-type]
        stream=str(desc.get("stream") or "synthetic-lifecycle"),  # type: ignore[arg-type]
        execution_mode=str(desc.get("execution_mode") or "container-worker"),
        credential_env_names=tuple(desc.get("credential_env_names") or ()),
        binary=str(desc.get("binary") or ""),
    )


def _describe_from_provider(impl: Any) -> dict[str, Any] | None:
    if impl is None:
        return None
    fn = getattr(impl, "describe", None)
    if callable(fn):
        try:
            out = fn() if impl is type(impl) else fn()
        except TypeError:
            try:
                out = impl.describe()  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                return None
        except Exception:  # noqa: BLE001
            return None
        return out if isinstance(out, dict) else None
    cls = impl if isinstance(impl, type) else type(impl)
    fn = getattr(cls, "describe", None)
    if callable(fn):
        try:
            out = fn()
        except TypeError:
            return None
        except Exception:  # noqa: BLE001
            return None
        return out if isinstance(out, dict) else None
    return None


def required_kinds_for_v014() -> frozenset[str]:
    """Historical name: coding-agent surface is now ACP."""
    return frozenset({"acp"})


def residual_kinds() -> frozenset[str]:
    return frozenset()
