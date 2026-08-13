"""SPI and graph types for the extension registry.

ExecutorSPI uses sync open/invoke/close to match existing AgentExecutor adapters
(AcpExecutor.invoke is sync). Hook handlers are async middleware with ``next``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TargetPlacement:
    """Core-owned L1 attach facts. Plugins bind; they do not pick container ids."""

    container_id: str
    uid: int
    gid: int
    workdir: str = "/attempt/workspace"
    home: str = "/attempt/home"
    shared_write: bool = False
    shared_gid: int | None = None


@runtime_checkable
class ExecutorSPI(Protocol):
    """Single-winner provider for the ``executor`` slot.

    Optional ``bind_to_target(placement) -> ExecutorSPI`` attaches the host
    SPI to a Core-owned L1 container. Missing bind → ``l1_executor_unbound``.
    """

    kind: str

    def open(self, **kwargs: Any) -> None:
        """Optional session open (default no-op on adapters that open lazily)."""
        ...

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> Any: ...

    def close(self) -> None:
        """Release process / session resources."""
        ...


# Middleware: async (ctx, value, next) -> value
NextFn = Callable[[Any], Awaitable[Any]]
HookHandler = Callable[[Any, Any, NextFn], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ExplicitBinding:
    """User / profile intent for one slot (short override, not full plugin copy)."""

    slot: str
    plugin: str
    priority: int | None = None
    replace_default: bool = False
    source: str = "explicit"


@dataclass
class BindingIntent:
    """Per-profile binding intent used at resolve / lock time."""

    profile_id: str
    executor: str | None = None  # sugar: executor slot selects this plugin's provide
    options: dict[str, Any] = field(default_factory=dict)
    extensions: list[ExplicitBinding] = field(default_factory=list)
    # Optional model / locator fields carried for factory materialize.
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRef:
    """Resolved single-winner provider (callable object, not a bare class name)."""

    plugin_id: str
    impl: Any
    priority: int
    source: str
    version: str | None = None
    digest: str | None = None
    replaced_default: bool = False
    slot: str = ""


@dataclass(frozen=True, slots=True)
class HandlerRef:
    """One link in a multi-slot chain."""

    plugin_id: str
    handler: Any
    priority: int
    source: str
    version: str | None = None
    digest: str | None = None
    replaced_default: bool = False
    slot: str = ""


@dataclass(frozen=True, slots=True)
class BindingRecord:
    """Lock-facing record of one resolved contribution."""

    slot: str
    kind: str  # "provide" | "on"
    plugin: str
    priority: int
    source: str
    version: str | None = None
    digest: str | None = None
    replaced_default: bool = False


@dataclass
class ExtensionGraph:
    """Session-pinned resolution result for one profile_id."""

    profile_id: str
    providers: dict[str, ProviderRef] = field(default_factory=dict)
    chains: dict[str, list[HandlerRef]] = field(default_factory=dict)
    records: list[BindingRecord] = field(default_factory=list)

    def provider(self, slot: str) -> ProviderRef | None:
        return self.providers.get(slot)

    def chain(self, slot: str) -> list[HandlerRef]:
        return list(self.chains.get(slot) or [])


def intent_from_profile(profile: Mapping[str, Any]) -> BindingIntent:
    """Build BindingIntent from a merged agent_profiles row or profiles binding."""
    profile_id = str(profile.get("id") or profile.get("profile_id") or "")
    executor_raw = profile.get("executor")
    executor = (
        str(executor_raw).strip()
        if isinstance(executor_raw, str) and executor_raw.strip()
        else None
    )
    options_raw = profile.get("options")
    options: dict[str, Any] = dict(options_raw) if isinstance(options_raw, Mapping) else {}
    extensions: list[ExplicitBinding] = []
    ext_raw = profile.get("extensions")
    if isinstance(ext_raw, Sequence) and not isinstance(ext_raw, (str, bytes)):
        for item in ext_raw:
            if not isinstance(item, Mapping):
                continue
            slot = item.get("slot")
            plugin = item.get("plugin")
            if not isinstance(slot, str) or not isinstance(plugin, str):
                continue
            prio = item.get("priority")
            extensions.append(
                ExplicitBinding(
                    slot=str(slot),
                    plugin=str(plugin),
                    priority=int(prio) if prio is not None else None,
                    replace_default=bool(item.get("replace_default")),
                    source="explicit",
                )
            )
    model_raw = profile.get("model")
    model = str(model_raw) if model_raw is not None else None
    base_url_raw = profile.get("base_url")
    base_url = (
        str(base_url_raw).strip()
        if isinstance(base_url_raw, str) and base_url_raw.strip()
        else None
    )
    api_key_raw = profile.get("api_key")
    api_key = (
        str(api_key_raw).strip() if isinstance(api_key_raw, str) and api_key_raw.strip() else None
    )
    return BindingIntent(
        profile_id=profile_id,
        executor=executor,
        options=options,
        extensions=extensions,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
