"""#71 C: env_* slots are executable middleware/SPI — not command-dict collectors."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from bora.application.attempt import extension_hooks as hooks
from bora.environment.manager import EnvironmentManager
from bora.plugins.defaults import register_defaults
from bora.plugins.protocol import BindingIntent, ExtensionSelect
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.resolve import resolve
from bora.plugins.slots import ENV_ACTION, ENV_INJECT, ENV_PREPARE_COMMANDS, ENV_TEARDOWN_COMMANDS


def _lock() -> Any:
    return SimpleNamespace(
        agent_profiles=[{"id": "p", "executor": "acp", "options": {"entry": "pi"}}]
    )


def test_env_prepare_handler_does_real_work_and_rewrites_handoff(tmp_path: Path) -> None:
    """Handler code creates a file and mutates handoff — host does not parse DSL rows."""
    reg = ExtensionRegistry()
    register_defaults(reg)
    marker = tmp_path / "post_setup.done"
    calls: list[str] = []

    async def after_prepare(ctx: Any, value: Any, nxt: Any) -> Any:
        calls.append("env_prepare_commands")
        out = await nxt(value)
        workdir = getattr(ctx, "workdir", None) or getattr(ctx, "package_root", None)
        assert workdir is not None
        marker.write_text("ok\n", encoding="utf-8")
        data = dict(out) if isinstance(out, dict) else {}
        data["post_setup"] = {"plugin": "spy-env", "ok": True, "path": str(marker)}
        return data

    async def inject(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("env_inject")
        out = await nxt(value)
        data = dict(out) if isinstance(out, dict) else {}
        data["injected"] = True
        return data

    async def teardown(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        calls.append("env_teardown_commands")
        return await nxt(value)

    reg.on(ENV_PREPARE_COMMANDS, "spy-env", after_prepare, priority=10, source="test")
    reg.on(ENV_INJECT, "spy-env", inject, priority=10, source="test")
    reg.on(ENV_TEARDOWN_COMMANDS, "spy-env", teardown, priority=10, source="test")
    graph = resolve(
        BindingIntent(
            profile_id="p",
            extension_selects=[ExtensionSelect(plugin="spy-env")],
        ),
        reg,
        materialize=True,
    )

    lock = _lock()
    handoff = {"ok": True, "resource": "postgresql"}
    ctx = SimpleNamespace(
        package_root=tmp_path,
        workdir=tmp_path,
        env_manager=MagicMock(),
        resource_id="postgresql:x",
    )
    with patch.object(hooks, "graph_for_lock", return_value=graph):
        out = hooks.hook_env_prepare(lock, handoff, ctx=ctx)
        out = hooks.hook_env_inject(lock, out, ctx=ctx)
        hooks.hook_env_teardown(lock, out, ctx=ctx)

    assert marker.is_file()
    assert out["post_setup"]["ok"] is True
    assert out["injected"] is True
    assert "env_prepare_commands" in calls
    assert "env_inject" in calls
    assert "env_teardown_commands" in calls
    # Explicit anti-pattern check: value is handoff dict, not a list of command rows.
    assert not isinstance(out, list)


def test_env_action_gate_denies_before_resource_effect() -> None:
    class DenyDrop:
        def check(self, resource_id: str, action_id: str, args: dict[str, Any]) -> dict[str, Any]:
            del resource_id, args
            if action_id == "drop_schema":
                return {"ok": False, "error": "policy_denied"}
            return {"ok": True}

    mgr = EnvironmentManager(attempt_id="a", action_limit=5, action_gate=DenyDrop())
    # Inject a fake resource without docker.
    fake = MagicMock()
    fake.action.return_value = {"ok": True, "rows": []}
    mgr._resources["postgresql:t"] = fake

    denied = mgr.action("postgresql:t", "drop_schema", {"sql": "DROP TABLE x"})
    assert denied["ok"] is False
    assert denied["error"] == "policy_denied"
    fake.action.assert_not_called()

    allowed = mgr.action("postgresql:t", "query", {"sql": "SELECT 1"})
    assert allowed["ok"] is True
    fake.action.assert_called_once()


def test_env_action_provide_materializes() -> None:
    reg = ExtensionRegistry()
    register_defaults(reg)

    class AllowAll:
        def check(self, resource_id: str, action_id: str, args: dict[str, Any]) -> dict[str, Any]:
            del resource_id, action_id, args
            return {"ok": True}

    def factory(**_kwargs: Any) -> AllowAll:
        return AllowAll()

    reg.provide(ENV_ACTION, "gate-plugin", factory, priority=10, source="test", is_factory=True)
    graph = resolve(
        BindingIntent(
            profile_id="p",
            extension_selects=[ExtensionSelect(plugin="gate-plugin")],
        ),
        reg,
        materialize=True,
    )
    lock = _lock()
    with patch.object(hooks, "graph_for_lock", return_value=graph):
        spi = hooks.hook_env_action(lock, {"op": "prepare"})
    assert hasattr(spi, "check")
    assert spi.check("r", "query", {})["ok"] is True
