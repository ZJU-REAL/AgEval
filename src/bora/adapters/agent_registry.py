"""Executor kind recognition — thin façade over the extension registry.

MVP (constitution §0): **no** parallel entry-point / builtin factory dual path.
``resolve_executor`` materializes the ``executor`` slot provide for *kind*
(plugin_id). ``discover_executor_kinds`` lists plugins that provide that slot.

The sole ``AgentExecutor`` Protocol lives in ``bora.adapters.agent_contract``.
"""

from __future__ import annotations

from typing import Any


def discover_executor_kinds() -> set[str]:
    """Return plugin ids that provide the ``executor`` slot (Recognition)."""
    from bora.plugins.bootstrap import ensure_bootstrapped
    from bora.plugins.slots import EXECUTOR

    reg = ensure_bootstrapped()
    return set(reg.plugins_for_slot(EXECUTOR))


def resolve_executor(
    kind: str,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    entry: str | None = None,
    entry_id: str | None = None,
    **_kw: Any,
) -> Any:
    """Materialize the executor provide for *kind* (plugin_id) via the registry.

    ``api_key`` is an environment variable *name* (locator), never a secret value.
    ``entry`` / ``entry_id`` select ACP entry when *kind* is ``acp``.
    """
    from bora.plugins.bootstrap import ensure_bootstrapped
    from bora.plugins.protocol import BindingIntent, ExtensionSelect
    from bora.plugins.resolve import resolve
    from bora.plugins.slots import EXECUTOR

    plugin_opts: dict[str, Any] = {}
    eid = entry or entry_id
    if eid:
        plugin_opts["entry"] = str(eid)
    for key in ("agent", "method", "entry"):
        if key in _kw and _kw[key] is not None:
            plugin_opts[key] = _kw[key]

    plugin_id = str(kind)
    selects = (
        [ExtensionSelect(plugin=plugin_id, options=plugin_opts or None)] if plugin_opts else []
    )
    reg = ensure_bootstrapped()
    intent = BindingIntent(
        profile_id="_resolve",
        executor=plugin_id,
        extension_selects=selects,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    try:
        graph = resolve(intent, reg, materialize=True)
    except Exception as exc:  # noqa: BLE001 — map to KeyError for inventory callers
        raise KeyError(kind) from exc
    pref = graph.providers.get(EXECUTOR)
    if pref is None or pref.impl is None:
        raise KeyError(kind)
    return pref.impl
