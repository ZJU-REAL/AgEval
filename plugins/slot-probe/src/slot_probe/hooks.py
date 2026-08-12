"""Multi-slot handlers: real effects + audit — not declaration DSL rows."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from slot_probe.audit import audit, probe_dir

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
POST_SETUP = PLUGIN_ROOT / "scripts" / "post_setup.sh"


async def before_agent_open(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("before_agent_open")
    return await nxt(value)


async def after_agent_open(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_open")
    return await nxt(value)


async def before_agent_invoke(ctx: Any, value: Any, nxt: Any) -> Any:
    if isinstance(value, str):
        value = value + "\n[slot-probe]"
    audit("before_agent_invoke", prompt_len=len(value) if isinstance(value, str) else None)
    return await nxt(value)


async def after_agent_invoke(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_invoke", ok=bool(getattr(value, "ok", None)))
    return await nxt(value)


async def normalize_agent_result(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    meta = getattr(out, "metadata", None)
    if isinstance(meta, dict):
        meta = dict(meta)
        meta["slot_probe_normalized"] = True
        try:
            out.metadata = meta
        except Exception:
            pass
    audit("normalize_agent_result")
    return out


async def before_agent_close(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("before_agent_close")
    return await nxt(value)


async def after_agent_close(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("after_agent_close")
    return await nxt(value)


async def trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        md = dict(out.get("metadata") or {})
        md.setdefault("trajectory_source", "slot-probe")
        out = {**out, "metadata": md}
    audit("trajectory_collect")
    return out


async def trajectory_enrich(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        md = dict(out.get("metadata") or {})
        md["slot_probe"] = "v1"
        md["slot_probe_enrich"] = True
        out = {**out, "metadata": md}
    audit("trajectory_enrich")
    return out


async def evidence_extra(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    items = list(out) if isinstance(out, list) else []
    items.append({"plugin": "slot-probe", "kind": "slot_probe_note", "payload": {"ok": True}})
    audit("evidence_extra", n=len(items))
    return items


async def after_env_prepare(ctx: Any, value: Any, nxt: Any) -> Any:
    """Tail of env prepare: run plugin shell, rewrite handoff (real SPI)."""
    value = await nxt(value)
    workdir = getattr(ctx, "workdir", None) or getattr(ctx, "package_root", None)
    workdir_p = Path(str(workdir)) if workdir else Path.cwd()
    if POST_SETUP.is_file():
        subprocess.run(
            ["bash", str(POST_SETUP)],
            check=True,
            cwd=str(workdir_p),
        )
    marker = workdir_p / "post_setup.ok"
    # Also copy marker into probe dir for easy host-side discovery after run.
    if marker.is_file():
        dest = probe_dir() / "post_setup.ok"
        dest.write_text(marker.read_text(encoding="utf-8"), encoding="utf-8")
    if isinstance(value, dict):
        value = {
            **value,
            "post_setup": {
                "plugin": "slot-probe",
                "ok": marker.is_file(),
                "path": str(marker),
            },
        }
    audit("env_prepare_commands", post_setup_ok=marker.is_file(), workdir=str(workdir_p))
    return value


async def env_inject(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        out = {**out, "slot_probe_inject": True, "slot_probe_plugin": "slot-probe"}
    audit("env_inject")
    return out


async def env_teardown(ctx: Any, value: Any, nxt: Any) -> Any:
    audit("env_teardown_commands")
    return await nxt(value)


async def evaluation_input_contribute(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        out = {**out, "slot_probe_eval_input": True}
    audit("evaluation_input_contribute")
    return out


async def score_postprocess(ctx: Any, value: Any, nxt: Any) -> Any:
    out = await nxt(value)
    if isinstance(out, dict):
        metrics = dict(out.get("metrics") or {})
        metrics["slot_probe"] = 1
        out = {**out, "metrics": metrics}
    audit("score_postprocess")
    return out
