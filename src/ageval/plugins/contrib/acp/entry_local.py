"""Entry-local ACP binds that do not speak ``session/set_config_option``.

``options.entry: grok-build`` applies ``model`` / ``reasoning_effort`` on the
stdio argv and records actuals from vendor ``_meta``. Other entries stay on
ACP config options.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

GROK_BUILD_ENTRY = "grok-build"

_ENTRY_DEFAULT = "entry-default"


def uses_entry_local_bind(entry_id: str) -> bool:
    return entry_id == GROK_BUILD_ENTRY


def acp_stdio_argv(
    entry_id: str,
    base: Sequence[str],
    *,
    model: str | None,
    reasoning_effort: str | None,
) -> list[str]:
    """Host and L1 share this argv. grok-build inserts flags before ``stdio``."""
    cmd = [str(part) for part in base]
    if not uses_entry_local_bind(entry_id):
        return cmd
    extra: list[str] = []
    model_s = (model or "").strip()
    if model_s and model_s != _ENTRY_DEFAULT:
        extra.extend(["--model", model_s])
    effort_s = (reasoning_effort or "").strip()
    if effort_s:
        extra.extend(["--reasoning-effort", effort_s])
    if not extra:
        return cmd
    if "stdio" in cmd:
        idx = cmd.index("stdio")
        return cmd[:idx] + extra + cmd[idx:]
    return cmd + extra


def apply_grok_build_bind(
    *,
    initialize: Any,
    session: Any,
    model: str | None,
    reasoning_effort: str | None,
) -> tuple[str, str | None]:
    """Validate requested ids against advertised ``_meta`` and return actuals.

    Raises ``RuntimeError`` with ``acp_model_unavailable`` /
    ``acp_reasoning_effort_unavailable`` when a requested exact id is missing
    or the process did not honor the argv bind.
    """
    desired_model = (model or "").strip() or _ENTRY_DEFAULT
    desired_effort = (reasoning_effort or "").strip() or None
    parsed = parse_grok_build_meta(initialize, session)
    advertised_models = parsed["advertised_models"]
    actual_model = parsed["actual_model"]
    actual_effort = parsed["actual_effort"]
    efforts_by_model: Mapping[str, list[str]] = parsed["efforts_by_model"]

    if desired_model != _ENTRY_DEFAULT:
        if desired_model not in advertised_models:
            raise RuntimeError("acp_model_unavailable")
        if actual_model is not None and actual_model != desired_model:
            raise RuntimeError("acp_model_unavailable")
        recorded_model = desired_model
    else:
        recorded_model = actual_model or _ENTRY_DEFAULT

    target_for_effort = recorded_model if recorded_model != _ENTRY_DEFAULT else None
    if target_for_effort and target_for_effort in efforts_by_model:
        advertised_efforts = list(efforts_by_model[target_for_effort])
    elif target_for_effort and target_for_effort in advertised_models:
        advertised_efforts = []
    else:
        advertised_efforts = list(parsed["advertised_efforts"])

    if desired_effort is not None:
        if desired_effort not in advertised_efforts:
            raise RuntimeError("acp_reasoning_effort_unavailable")
        if actual_effort is not None and actual_effort != desired_effort:
            raise RuntimeError("acp_reasoning_effort_unavailable")
        recorded_effort = desired_effort
    else:
        recorded_effort = actual_effort

    return recorded_model, recorded_effort


def parse_grok_build_meta(initialize: Any, session: Any) -> dict[str, Any]:
    """Read advertised lists and selected rows from grok vendor ``_meta``."""
    init_meta = _meta_of(initialize)
    session_meta = _meta_of(session)
    model_state = _as_mapping(init_meta.get("modelState"))
    available = model_state.get("availableModels")
    if not isinstance(available, list):
        available = []

    advertised_models: list[str] = []
    models_by_id: dict[str, Mapping[str, Any]] = {}
    for raw in available:
        row = _as_mapping(raw)
        mid = _first_str(row, "modelId", "model_id", "id")
        if mid is None:
            continue
        advertised_models.append(mid)
        models_by_id[mid] = row

    current = _first_str(model_state, "currentModelId", "current_model_id")
    session_cfg = _as_mapping(session_meta.get("x.ai/sessionConfig"))
    selected_model, selected_effort, cfg_models, cfg_efforts = _session_config_selected(session_cfg)
    detail = _as_mapping(session_meta.get("x.ai/sessionDetail"))
    detail_model = _first_str(detail, "currentModelId", "current_model_id")

    actual_model = selected_model or current or detail_model
    for mid in cfg_models:
        if mid not in models_by_id:
            advertised_models.append(mid)

    efforts_by_model: dict[str, list[str]] = {}
    for mid, row in models_by_id.items():
        efforts = _efforts_for_model(row)
        if efforts:
            efforts_by_model[mid] = efforts
    target_model = actual_model
    advertised_efforts = list(efforts_by_model.get(target_model or "", []))
    if not advertised_efforts:
        advertised_efforts = list(cfg_efforts)

    return {
        "advertised_models": advertised_models,
        "advertised_efforts": advertised_efforts,
        "efforts_by_model": efforts_by_model,
        "actual_model": actual_model,
        "actual_effort": selected_effort,
    }


def _efforts_for_model(row: Mapping[str, Any] | None) -> list[str]:
    if row is None:
        return []
    meta = _as_mapping(row.get("_meta") or row.get("meta"))
    raw = meta.get("reasoningEfforts") or meta.get("reasoning_efforts")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        mapping = _as_mapping(item)
        val = _first_str(mapping, "id", "value")
        if val is not None:
            out.append(val)
    return out


def _session_config_selected(
    session_cfg: Mapping[str, Any],
) -> tuple[str | None, str | None, list[str], list[str]]:
    raw_opts = session_cfg.get("options")
    if not isinstance(raw_opts, list):
        return None, None, [], []
    models: list[str] = []
    efforts: list[str] = []
    selected_model: str | None = None
    selected_effort: str | None = None
    for raw in raw_opts:
        opt = _as_mapping(raw)
        oid = _first_str(opt, "id", "value")
        if oid is None:
            continue
        category = str(opt.get("category") or "")
        selected = bool(opt.get("selected"))
        if category == "model":
            models.append(oid)
            if selected:
                selected_model = oid
        elif category == "mode":
            efforts.append(oid)
            if selected:
                selected_effort = oid
    return selected_model, selected_effort, models, efforts


def _meta_of(obj: Any) -> dict[str, Any]:
    for name in ("_meta", "meta", "field_meta"):
        attr = getattr(obj, name, None)
        if isinstance(attr, dict):
            return dict(attr)
    data = _as_mapping(obj)
    for name in ("_meta", "meta", "field_meta"):
        meta = data.get(name)
        if isinstance(meta, dict):
            return dict(meta)
    return {}


def _as_mapping(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    dumped = getattr(obj, "model_dump", None)
    if callable(dumped):
        try:
            raw = dumped(by_alias=True, exclude_none=False)
        except TypeError:
            raw = dumped()
        if isinstance(raw, dict):
            return dict(raw)
    return {}


def _first_str(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key not in data:
            continue
        val = data[key]
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return None
