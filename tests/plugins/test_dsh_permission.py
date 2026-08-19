"""dsh options.permission: composition swap, env, fail-closed (no live DSH)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ageval.plugins.errors import ExtensionMaterializeError

_DSH_SRC = Path(__file__).resolve().parents[2] / "plugins" / "dsh" / "src"
if str(_DSH_SRC) not in sys.path:
    sys.path.insert(0, str(_DSH_SRC))

from dsh_plugin.container import DshContainerExecutor  # noqa: E402
from dsh_plugin.factory import (  # noqa: E402
    DEFAULT_COMPOSITION,
    PERMISSION_ENV,
    SANDBOXED_COMPOSITION,
    DshExecutorSPI,
    build_executor,
    permission_child_env,
    resolve_composition_path,
    resolve_effective_composition,
    resolve_permission,
)


def test_resolve_permission_omit_and_blank() -> None:
    assert resolve_permission(None) is None
    assert resolve_permission("") is None
    assert resolve_permission("   ") is None


@pytest.mark.parametrize("mode", ["read-only", "workspace-write", "danger-full-access"])
def test_resolve_permission_allows_known_modes(mode: str) -> None:
    assert resolve_permission(mode) == mode
    assert resolve_permission(f"  {mode}  ") == mode


def test_resolve_permission_rejects_unknown() -> None:
    with pytest.raises(ExtensionMaterializeError, match="dsh_permission_invalid:ask"):
        resolve_permission("ask")
    with pytest.raises(ExtensionMaterializeError, match="dsh_permission_invalid"):
        resolve_permission(1)


def test_permission_selects_sandboxed_unless_custom_composition() -> None:
    assert (
        resolve_effective_composition(composition=None, permission="read-only")
        == SANDBOXED_COMPOSITION
    )
    assert (
        resolve_effective_composition(composition="slim", permission="workspace-write")
        == SANDBOXED_COMPOSITION
    )
    assert (
        resolve_effective_composition(composition="sandboxed", permission="read-only")
        == SANDBOXED_COMPOSITION
    )
    assert resolve_effective_composition(composition="custom", permission="read-only") == "custom"
    assert resolve_effective_composition(composition=None, permission=None) == DEFAULT_COMPOSITION
    assert resolve_effective_composition(composition="slim", permission=None) == "slim"


def test_sandboxed_composition_file_exists() -> None:
    path = resolve_composition_path(SANDBOXED_COMPOSITION)
    text = path.read_text(encoding="utf-8")
    assert "dsh-fs-sandbox" in text
    assert "dsh-sandbox-policy" in text
    assert "DSH_PERMISSION_MODE" in text
    assert "policy: never" in text
    assert "name: '@deepseek-ai/dsh-bash-local'" in text
    assert "name: '@deepseek-ai/dsh-fs-sandbox'" in text
    assert "name: '@deepseek-ai/dsh-bash-sandbox'" not in text
    assert "name: '@deepseek-ai/dsh-fs-local'" not in text


def test_factory_permission_switches_composition_and_bind_env() -> None:
    spi = build_executor(
        options={"permission": "read-only"},
        model="deepseek-v4-flash",
        api_key="deepseek_api_key",
        profile_id="solver",
    )
    assert spi.permission == "read-only"
    assert spi.composition == SANDBOXED_COMPOSITION
    bound = spi.bind_to_target(
        SimpleNamespace(
            container_id="cid123",
            uid=10001,
            gid=10001,
            workdir="/attempt/workspace",
            home="/attempt/home",
        )
    )
    assert isinstance(bound, DshContainerExecutor)
    assert bound.permission == "read-only"
    assert bound.composition == SANDBOXED_COMPOSITION
    assert bound.cordis_container == "/opt/dsh/compositions/sandboxed.cordis.yml"
    env = bound._child_env()
    assert env[PERMISSION_ENV] == "read-only"
    assert env["DSH_CORDIS_CONFIG"] == bound.cordis_container


def test_omitted_permission_keeps_slim() -> None:
    spi = DshExecutorSPI(options={"composition": "slim"})
    assert spi.permission is None
    assert spi.composition == "slim"
    bound = spi.bind_to_target(
        SimpleNamespace(
            container_id="cid123",
            uid=10001,
            gid=10001,
            workdir="/attempt/workspace",
            home="/attempt/home",
        )
    )
    assert bound.permission is None
    assert bound.composition == "slim"
    assert bound.cordis_container == "/opt/dsh/compositions/slim.cordis.yml"
    env = bound._child_env()
    assert PERMISSION_ENV not in env


def test_invalid_permission_raises_before_spawn() -> None:
    with pytest.raises(ExtensionMaterializeError, match="dsh_permission_invalid:rwx"):
        DshExecutorSPI(options={"permission": "rwx"})
    with pytest.raises(ExtensionMaterializeError, match="dsh_permission_invalid:rwx"):
        DshContainerExecutor(container_id="cid", permission="rwx")


def test_host_invoke_forwards_permission_env(monkeypatch: object) -> None:
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)  # type: ignore[attr-defined]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")  # type: ignore[attr-defined]
    harness = MagicMock()
    session = MagicMock()
    session.run.return_value = SimpleNamespace(
        events=[],
        notifications=(),
        final_response="ok",
        finish_reason="completed",
        session_id="s1",
        session_root="/tmp/dsh",
    )
    harness.start_session.return_value = session

    captured: dict[str, object] = {}

    def _factory(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return harness

    fake_mod = MagicMock()
    fake_mod.DeepSeekHarness = _factory
    spi = DshExecutorSPI(options={"permission": "workspace-write"}, model="deepseek-v4-flash")
    with patch.dict(sys.modules, {"deepseek_harness": fake_mod}):
        result = spi.invoke("hello", timeout=5.0)
    assert result.ok
    env = captured.get("env")
    assert isinstance(env, dict)
    assert env[PERMISSION_ENV] == "workspace-write"
    cordis = str(captured.get("cordis") or "")
    assert cordis.endswith("sandboxed.cordis.yml")
    assert result.metadata is not None
    assert result.metadata.get("composition") == SANDBOXED_COMPOSITION
    assert result.metadata.get("permission") == "workspace-write"


def test_permission_child_env_empty_when_unset() -> None:
    assert permission_child_env(None) == {}
    assert permission_child_env("read-only") == {PERMISSION_ENV: "read-only"}
