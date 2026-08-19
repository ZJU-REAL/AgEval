"""#71 B: trajectory_collect/enrich/seal + evidence_extra participate in seal write."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ageval.plugins.defaults import register_defaults
from ageval.plugins.protocol import BindingIntent, ExtensionSelect
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.slots import (
    EVIDENCE_EXTRA,
    TRAJECTORY_COLLECT,
    TRAJECTORY_ENRICH,
)
from ageval.runtime.agent_service_evidence import seal_invoke_result


class _FakeResult:
    ok = True
    error = None
    text = "final-answer"
    structured = None
    events: tuple = ()
    usage = None
    model = "m"
    metadata: dict = {}
    source_refs: tuple = ()
    stderr = ""


class _FakeHandle:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.store = None
        self.sealed: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []

    def append_event(self, ev: dict[str, Any]) -> None:
        self.events.append(ev)

    def write_stderr(self, _text: str) -> None:
        return None

    def seal(self, **kwargs: Any) -> None:
        self.sealed = dict(kwargs)


def test_trajectory_chain_enriches_metadata_and_evidence_extra(tmp_path: Path) -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    calls: list[str] = []

    async def collect(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("trajectory_collect")
        out = await nxt(value)
        if isinstance(out, dict):
            md = dict(out.get("metadata") or {})
            md["collected"] = True
            return {**out, "metadata": md}
        return out

    async def enrich(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("trajectory_enrich")
        out = await nxt(value)
        if isinstance(out, dict):
            md = dict(out.get("metadata") or {})
            md["enriched"] = "plugin-x"
            return {**out, "metadata": md}
        return out

    async def extras(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("evidence_extra")
        out = await nxt(value)
        items = list(out) if isinstance(out, list) else []
        items.append({"plugin": "spy", "kind": "note", "payload": {"k": 1}})
        return items

    reg.on(TRAJECTORY_COLLECT, "spy", collect, priority=10, source="test")
    reg.on(TRAJECTORY_ENRICH, "spy", enrich, priority=10, source="test")
    reg.on(EVIDENCE_EXTRA, "spy", extras, priority=10, source="test")
    # trajectory_seal provide stays on default marker

    graph = resolve(
        BindingIntent(profile_id="p", extension_selects=[ExtensionSelect(plugin="spy")]),
        reg,
        materialize=True,
    )
    inv_dir = tmp_path / "inv_001"
    inv_dir.mkdir()
    handle = _FakeHandle(inv_dir)
    err = seal_invoke_result(
        handle,
        result=_FakeResult(),
        prompt="hello",
        kind="fake",
        turn_index=1,
        latency_ms=12.0,
        extension_graph=graph,
        extension_ctx={"attempt_id": "a1"},
    )
    assert err is None
    assert "trajectory_collect" in calls
    assert "trajectory_enrich" in calls
    assert "evidence_extra" in calls

    traj = inv_dir / "trajectory.jsonl"
    assert traj.is_file()
    lines = [json.loads(line) for line in traj.read_text(encoding="utf-8").splitlines() if line]
    # Metadata enrichment must be visible on written trajectory (terminal/meta rows).
    blob = "\n".join(json.dumps(row, sort_keys=True) for row in lines)
    assert (
        "enriched" in blob
        or any(
            isinstance(row.get("metadata"), dict) and row["metadata"].get("enriched") == "plugin-x"
            for row in lines
        )
        or any(
            row.get("type") == "terminal"
            and isinstance(row.get("metadata"), dict)
            and row["metadata"].get("enriched") == "plugin-x"
            for row in lines
        )
    )
    # Also accept enrichment on user/assistant metadata if writer places it there.
    # Fallback: inspect write via seal final_response seal_marker from default provide.
    assert handle.sealed is not None
    final = handle.sealed.get("final_response") or {}
    assert isinstance(final.get("trajectory_seal"), dict)
    assert final["trajectory_seal"].get("seal") == "default_authority_shape"

    extra_path = inv_dir / "evidence_extra.jsonl"
    assert extra_path.is_file()
    extra_rows = [
        json.loads(line) for line in extra_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert any(r.get("plugin") == "spy" for r in extra_rows)


def test_trajectory_rewrite_on_collect_changes_prompt_written(tmp_path: Path) -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)

    async def collect(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        out = await nxt(value)
        if isinstance(out, dict):
            return {**out, "prompt": f"{out.get('prompt')}|tagged"}
        return out

    reg.on(TRAJECTORY_COLLECT, "spy", collect, priority=10, source="test")
    graph = resolve(
        BindingIntent(profile_id="p", extension_selects=[ExtensionSelect(plugin="spy")]),
        reg,
        materialize=True,
    )
    inv_dir = tmp_path / "inv_002"
    inv_dir.mkdir()
    handle = _FakeHandle(inv_dir)
    seal_invoke_result(
        handle,
        result=_FakeResult(),
        prompt="raw",
        kind="fake",
        turn_index=1,
        latency_ms=1.0,
        extension_graph=graph,
    )
    text = (inv_dir / "trajectory.jsonl").read_text(encoding="utf-8")
    assert "raw|tagged" in text or "tagged" in text
