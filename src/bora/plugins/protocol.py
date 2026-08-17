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
    options: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ExtensionSelect:
    """One ``profiles.extensions`` row before per-slot expansion.

    ``slots is None`` means every slot that plugin registered (provide + on).
    """

    plugin: str
    slots: tuple[str, ...] | None = None
    priority: int | None = None
    replace_default: bool = False
    source: str = "explicit"
    options: Mapping[str, Any] | None = None


@dataclass
class BindingIntent:
    """Per-profile binding intent used at resolve / lock time."""

    profile_id: str
    executor: str | None = None  # sugar: executor slot selects this plugin's provide
    options: dict[str, Any] = field(default_factory=dict)
    extensions: list[ExplicitBinding] = field(default_factory=list)
    extension_selects: list[ExtensionSelect] = field(default_factory=list)
    # Optional model / locator fields carried for factory materialize.
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    package_root: str | None = None
    workdir: str | None = None
    home: str | None = None


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
    options: Mapping[str, Any] | None = None


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
    options: Mapping[str, Any] | None = None


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
    extension_selects: list[ExtensionSelect] = []
    ext_raw = profile.get("extensions")
    if ext_raw is None:
        ext_raw = []
    if not isinstance(ext_raw, Sequence) or isinstance(ext_raw, (str, bytes)):
        from bora.plugins.errors import ExtensionRegistryError

        raise ExtensionRegistryError(
            "extensions must be a list of mappings",
            kind="invalid_extension_binding",
        )
    for item in ext_raw:
        parsed_binding, parsed_select = parse_extension_row(item)
        if parsed_binding is not None:
            extensions.append(parsed_binding)
        if parsed_select is not None:
            extension_selects.append(parsed_select)
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
    package_root = _optional_str(profile.get("_package_root") or profile.get("package_root"))
    workdir = _optional_str(profile.get("_workdir") or profile.get("workdir"))
    home = _optional_str(profile.get("_home") or profile.get("home"))
    return BindingIntent(
        profile_id=profile_id,
        executor=executor,
        options=options,
        extensions=extensions,
        extension_selects=extension_selects,
        model=model,
        base_url=base_url,
        api_key=api_key,
        package_root=package_root,
        workdir=workdir,
        home=home,
    )


def _optional_str(raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def row_options(item: Mapping[str, Any]) -> dict[str, Any]:
    """Parse optional ``options`` on one extensions row. Missing → empty map."""
    raw = item.get("options")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        from bora.plugins.errors import ExtensionRegistryError

        raise ExtensionRegistryError(
            "extensions.options must be a mapping",
            kind="invalid_extension_binding",
        )
    return dict(raw)


def options_for_plugin(intent: BindingIntent, plugin_id: str) -> dict[str, Any]:
    """Last matching extensions row for *plugin_id* wins (same dest last-writer)."""
    found: dict[str, Any] = {}
    for sel in intent.extension_selects:
        if sel.plugin == plugin_id and sel.options:
            found = dict(sel.options)
    for binding in intent.extensions:
        if binding.plugin == plugin_id and binding.options:
            found = dict(binding.options)
    return found


def parse_extension_row(item: Any) -> tuple[ExplicitBinding | None, ExtensionSelect | None]:
    """Parse one extensions row. ``{slot, plugin}`` is a single-slot binding."""
    from bora.plugins.errors import ExtensionRegistryError

    if not isinstance(item, Mapping):
        raise ExtensionRegistryError(
            "each extensions row must be a mapping",
            kind="invalid_extension_binding",
        )
    plugin_raw = item.get("plugin")
    if not isinstance(plugin_raw, str) or not plugin_raw.strip():
        raise ExtensionRegistryError(
            "extensions row requires plugin",
            kind="invalid_extension_binding",
        )
    plugin = plugin_raw.strip()
    slot_raw = item.get("slot")
    slots_raw = item.get("slots")
    prio = item.get("priority")
    priority = int(prio) if prio is not None else None
    replace_default = bool(item.get("replace_default"))
    options = row_options(item)
    if slot_raw is not None and slots_raw is not None:
        raise ExtensionRegistryError(
            "extensions row cannot set both slot and slots",
            kind="invalid_extension_binding",
        )
    if slot_raw is not None:
        if not isinstance(slot_raw, str) or not slot_raw.strip():
            raise ExtensionRegistryError(
                "extensions.slot must be a non-empty string",
                kind="invalid_extension_binding",
            )
        return (
            ExplicitBinding(
                slot=slot_raw.strip(),
                plugin=plugin,
                priority=priority,
                replace_default=replace_default,
                source="explicit",
                options=options or None,
            ),
            None,
        )
    if slots_raw is not None:
        if not isinstance(slots_raw, Sequence) or isinstance(slots_raw, (str, bytes)):
            raise ExtensionRegistryError(
                "extensions.slots must be a list of slot ids",
                kind="invalid_extension_binding",
            )
        if not slots_raw:
            raise ExtensionRegistryError(
                "extensions.slots must not be empty",
                kind="invalid_extension_binding",
            )
        slots: list[str] = []
        for slot in slots_raw:
            if not isinstance(slot, str) or not slot.strip():
                raise ExtensionRegistryError(
                    "extensions.slots entries must be non-empty strings",
                    kind="invalid_extension_binding",
                )
            slots.append(slot.strip())
        return (
            None,
            ExtensionSelect(
                plugin=plugin,
                slots=tuple(slots),
                priority=priority,
                replace_default=replace_default,
                options=options or None,
            ),
        )
    return (
        None,
        ExtensionSelect(
            plugin=plugin,
            slots=None,
            priority=priority,
            replace_default=replace_default,
            options=options or None,
        ),
    )
