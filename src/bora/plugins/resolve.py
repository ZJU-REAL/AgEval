"""Resolve BindingIntent + registry → ExtensionGraph (session pin / lock source)."""

from __future__ import annotations

from typing import Any

from bora.plugins.conflict import order_chain, pick_one
from bora.plugins.errors import (
    ExtensionMaterializeError,
    ExtensionPluginNotFoundError,
    UnknownExtensionSlotError,
)
from bora.plugins.protocol import (
    BindingIntent,
    BindingRecord,
    ExplicitBinding,
    ExtensionGraph,
    ExtensionSelect,
    HandlerRef,
    ProviderRef,
)
from bora.plugins.registry import ExtensionRegistry, Registration
from bora.plugins.slots import ALL_PUBLIC_SLOTS, EXECUTOR, SlotKind, get_slot_kind, is_public_slot


def resolve(
    intent: BindingIntent,
    registry: ExtensionRegistry,
    *,
    materialize: bool = True,
) -> ExtensionGraph:
    """Resolve all public slots for one profile intent.

    When ``materialize`` is False, provider/handler refs keep Registration
    wrappers (useful for lock-only serialization without constructing executors).
    """
    graph = ExtensionGraph(profile_id=intent.profile_id)
    explicit = list(intent.extensions)
    explicit.extend(expand_extension_selects(intent.extension_selects, registry))
    for binding in explicit:
        if not is_public_slot(binding.slot):
            raise UnknownExtensionSlotError(
                f"unknown extension slot: {binding.slot!r}",
                kind="unknown_extension_slot",
            )

    # Sugar: profiles executor: <plugin_id> → explicit binding for executor slot.
    # Appended last so it wins over an all-slots ``- plugin:`` row.
    if intent.executor:
        explicit.append(
            ExplicitBinding(
                slot=EXECUTOR,
                plugin=str(intent.executor),
                source="profile_executor_field",
            )
        )

    for slot in ALL_PUBLIC_SLOTS:
        kind = get_slot_kind(slot)
        raw_candidates = registry.candidates(slot)
        # Expand Registration-backed candidates for conflict helpers.
        candidates = list(raw_candidates)
        slot_explicit = [e for e in explicit if e.slot == slot]

        if kind is SlotKind.PROVIDE:
            if slot != EXECUTOR and not slot_explicit:
                candidates = [c for c in candidates if _auto_on_provide(c)]
            if not candidates and not slot_explicit:
                # Optional provide slots may be empty (e.g. env_action when unused).
                # executor is required when profiles set executor field (handled by
                # pick_one raising plugin_not_found).
                if slot == EXECUTOR and intent.executor:
                    pick_one([], slot_explicit, slot=slot)  # raises
                continue
            if not candidates and not slot_explicit:
                continue
            try:
                winner = pick_one(candidates, explicit, slot=slot)
            except Exception:
                # Re-raise; empty optional provide without intent is skip only above.
                if not candidates and not slot_explicit:
                    continue
                raise
            reg = winner.impl
            if not isinstance(reg, Registration):
                raise ExtensionMaterializeError(
                    f"invalid registration object for {slot}",
                    kind="extension_materialize_failed",
                )
            impl = _materialize(reg, intent) if materialize else reg.impl
            # replaced_default if a default candidate existed and winner is not default.
            replaced_default = any(c.is_default for c in candidates) and not winner.is_default
            pref = ProviderRef(
                plugin_id=winner.plugin_id,
                impl=impl,
                priority=winner.priority,
                source=winner.source,
                version=winner.version,
                digest=winner.digest,
                replaced_default=replaced_default,
                slot=slot,
            )
            graph.providers[slot] = pref
            graph.records.append(
                BindingRecord(
                    slot=slot,
                    kind="provide",
                    plugin=winner.plugin_id,
                    priority=winner.priority,
                    source=winner.source,
                    version=winner.version,
                    digest=winner.digest,
                    replaced_default=replaced_default,
                )
            )
        else:
            # multi
            if not candidates and not slot_explicit:
                continue
            chain = order_chain(candidates, explicit, slot=slot)
            refs: list[HandlerRef] = []
            for item in chain:
                reg = item.impl
                if not isinstance(reg, Registration):
                    raise ExtensionMaterializeError(
                        f"invalid registration object for {slot}",
                        kind="extension_materialize_failed",
                    )
                handler = _materialize(reg, intent) if materialize else reg.impl
                href = HandlerRef(
                    plugin_id=item.plugin_id,
                    handler=handler,
                    priority=item.priority,
                    source=item.source,
                    version=item.version,
                    digest=item.digest,
                    replaced_default=False,
                    slot=slot,
                )
                refs.append(href)
                graph.records.append(
                    BindingRecord(
                        slot=slot,
                        kind="on",
                        plugin=item.plugin_id,
                        priority=item.priority,
                        source=item.source,
                        version=item.version,
                        digest=item.digest,
                        replaced_default=False,
                    )
                )
            graph.chains[slot] = refs

    return graph


def _materialize(reg: Registration, intent: BindingIntent) -> Any:
    """If registration is a factory, construct with intent options; else return impl."""
    impl = reg.impl
    if not reg.is_factory:
        return impl
    if not callable(impl):
        raise ExtensionMaterializeError(
            f"factory for plugin {reg.plugin_id!r} slot {reg.slot!r} is not callable",
            kind="extension_materialize_failed",
        )
    try:
        return impl(
            options=dict(intent.options),
            profile_id=intent.profile_id,
            model=intent.model,
            base_url=intent.base_url,
            api_key=intent.api_key,
            plugin_id=reg.plugin_id,
        )
    except TypeError:
        try:
            return impl(options=dict(intent.options), profile_id=intent.profile_id)
        except TypeError:
            try:
                return impl()
            except Exception as exc:  # noqa: BLE001
                raise ExtensionMaterializeError(
                    f"materialize failed for plugin {reg.plugin_id!r} slot {reg.slot!r}: {exc}",
                    kind="extension_materialize_failed",
                ) from exc
    except ExtensionMaterializeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtensionMaterializeError(
            f"materialize failed for plugin {reg.plugin_id!r} slot {reg.slot!r}: {exc}",
            kind="extension_materialize_failed",
        ) from exc


def resolve_for_lock(
    intent: BindingIntent,
    registry: ExtensionRegistry,
) -> ExtensionGraph:
    """Resolve without constructing heavy SPI instances (lock field only)."""
    return resolve(intent, registry, materialize=False)


def expand_extension_selects(
    selects: list[ExtensionSelect],
    registry: ExtensionRegistry,
) -> list[ExplicitBinding]:
    """Turn ``- plugin:`` / ``slots:`` rows into per-slot explicit bindings."""
    out: list[ExplicitBinding] = []
    for sel in selects:
        registered = registry.slots_for_plugin(sel.plugin)
        if not registered:
            raise ExtensionPluginNotFoundError(
                f"plugin {sel.plugin!r} is not registered",
                kind="extension_plugin_not_found",
            )
        if sel.slots is None:
            wanted = list(registered)
        else:
            wanted = []
            for slot in sel.slots:
                if not is_public_slot(slot):
                    raise UnknownExtensionSlotError(
                        f"unknown extension slot: {slot!r}",
                        kind="unknown_extension_slot",
                    )
                if slot not in registered:
                    raise ExtensionPluginNotFoundError(
                        f"plugin {sel.plugin!r} did not register slot {slot!r}",
                        kind="extension_slot_unregistered",
                    )
                wanted.append(slot)
        for slot in wanted:
            out.append(
                ExplicitBinding(
                    slot=slot,
                    plugin=sel.plugin,
                    priority=sel.priority,
                    replace_default=sel.replace_default,
                    source=sel.source,
                )
            )
    return out


def _auto_on_provide(candidate: Any) -> bool:
    return bool(getattr(candidate, "is_default", False)) or getattr(candidate, "source", "") in {
        "default",
        "first-party",
    }
