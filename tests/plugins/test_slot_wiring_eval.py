"""#71 D: evaluation_input_contribute / evaluation_runtime / score_postprocess emit."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from bora.application.attempt import extension_hooks as hooks
from bora.plugins.defaults import register_defaults
from bora.plugins.lock_bind import extension_graph_to_lock
from bora.plugins.protocol import BindingIntent, ExtensionSelect
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.resolve import resolve
from bora.plugins.slots import EVALUATION_INPUT_CONTRIBUTE, EVALUATION_RUNTIME, SCORE_POSTPROCESS


def _lock() -> Any:
    return SimpleNamespace(
        agent_profiles=[{"id": "p", "executor": "acp", "options": {"entry": "pi"}}]
    )


def test_evaluation_input_and_score_postprocess_rewrite() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)
    calls: list[str] = []

    async def ein(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("evaluation_input_contribute")
        out = await nxt(value)
        if isinstance(out, dict):
            arts = dict(out.get("artifacts") or {})
            arts["extra"] = "/tmp/extra.json"
            return {**out, "artifacts": arts}
        return out

    async def spp(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("score_postprocess")
        out = await nxt(value)
        if isinstance(out, dict):
            metrics = dict(out.get("metrics") or {})
            metrics["post"] = 1
            return {**out, "metrics": metrics}
        return out

    reg.on(EVALUATION_INPUT_CONTRIBUTE, "spy", ein, priority=10, source="test")
    reg.on(SCORE_POSTPROCESS, "spy", spp, priority=10, source="test")
    graph = resolve(
        BindingIntent(profile_id="p", extension_selects=[ExtensionSelect(plugin="spy")]),
        reg,
        materialize=True,
    )

    lock = _lock()
    with patch.object(hooks, "graph_for_lock", return_value=graph):
        contrib = hooks.hook_evaluation_input(lock, {"artifacts": {"a": "/x"}})
        runtime = hooks.hook_evaluation_runtime(lock, {"source": "test"})
        scored = hooks.hook_score_postprocess(lock, {"status": "PASS", "score": 1.0, "metrics": {}})

    assert "evaluation_input_contribute" in calls
    assert "score_postprocess" in calls
    assert contrib["artifacts"]["extra"] == "/tmp/extra.json"
    assert isinstance(runtime, dict)
    assert runtime.get("runtime") == "package"
    assert scored["metrics"]["post"] == 1


def test_l3_bindings_appear_in_lock_fragment() -> None:
    """Score-affecting L3 slots must be lock-visible when plugins contribute."""
    reg = ExtensionRegistry()
    register_defaults(reg)

    async def spp(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        return await nxt(value)

    reg.on(SCORE_POSTPROCESS, "score-spy", spp, priority=50, source="test")
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            extension_selects=[ExtensionSelect(plugin="score-spy")],
        ),
        reg,
        materialize=False,
    )
    frag = extension_graph_to_lock(graph)
    assert SCORE_POSTPROCESS in frag
    assert frag[SCORE_POSTPROCESS]["kind"] == "on"
    plugins = [c["plugin"] for c in frag[SCORE_POSTPROCESS]["chain"]]
    assert "score-spy" in plugins
    assert EVALUATION_RUNTIME in frag
    assert frag[EVALUATION_RUNTIME]["kind"] == "provide"
    assert EVALUATION_INPUT_CONTRIBUTE in frag
