"""dsh invoke goes through the environment Protocol, not a host SDK."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.helpers.box import local_box

from ageval.environments.protocol import EnvironmentCapabilities
from ageval.plugins.errors import InjectUnsatisfiedError
from ageval.plugins.manifest import load_manifest
from ageval.plugins.protocol import BindingIntent, InjectRequirement
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.resolve import resolve
from ageval.plugins.slots import ENVIRONMENT, EXECUTOR

ROOT = Path(__file__).resolve().parents[2]
_DSH_SRC = ROOT / "plugins" / "dsh" / "src"
if str(_DSH_SRC) not in sys.path:
    sys.path.insert(0, str(_DSH_SRC))

from dsh_plugin.container import DshBoxExecutor  # noqa: E402
from dsh_plugin.factory import build_executor  # noqa: E402


class SpyHost:
    """Local box that records exec argv/env, then runs them for real."""

    def __init__(self, attempt_root: Path) -> None:
        self._inner = local_box(attempt_root)
        self.commands: list[tuple[list[str], dict[str, str] | None]] = []
        self.uploads: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def start(self, *, force_build: bool = False) -> None:
        await self._inner.start(force_build=force_build)

    async def stop(self, *, delete: bool) -> None:
        await self._inner.stop(delete=delete)

    async def upload(self, source: Path, dest: str) -> None:
        self.uploads.append(dest)
        await self._inner.upload(source, dest)

    async def exec(self, command, **kwargs: Any):  # type: ignore[no-untyped-def]
        env = kwargs.get("env")
        self.commands.append((list(command), dict(env) if env else None))
        return await self._inner.exec(command, **kwargs)


def test_manifest_injects_environment_exec_and_upload() -> None:
    manifest = load_manifest(ROOT / "plugins" / "dsh")
    assert len(manifest.inject) == 1
    row = manifest.inject[0]
    assert row.service == "environment"
    assert set(row.capabilities) == {"exec", "upload"}


def test_factory_returns_box_executor() -> None:
    host = local_box("/nowhere")
    executor = build_executor(
        host=host,
        placement=host.placement(),
        model="deepseek-v4-flash",
        api_key="litellm_api_key",
    )
    assert isinstance(executor, DshBoxExecutor)
    assert executor.kind == "dsh"


def test_lock_fails_when_environment_cannot_exec() -> None:
    class MuteHost:
        capabilities = EnvironmentCapabilities(upload=True)

    registry = ExtensionRegistry()
    registry.exclusive(ENVIRONMENT, "mute", MuteHost, source="test", is_factory=True)
    registry.exclusive(EXECUTOR, "dsh", build_executor, source="test", is_factory=True)
    registry.declare_inject(
        "dsh",
        (InjectRequirement(service=ENVIRONMENT, capabilities=("exec", "upload")),),
    )
    with pytest.raises(InjectUnsatisfiedError, match="exec"):
        resolve(
            BindingIntent(profile_id="solver", environment="mute", executor="dsh"),
            registry,
        )


def test_lock_records_inject_when_box_can_exec() -> None:
    from ageval.plugins.contrib.local.host import LocalHost

    registry = ExtensionRegistry()
    registry.exclusive(ENVIRONMENT, "local", LocalHost, source="test", is_factory=True)
    registry.exclusive(EXECUTOR, "dsh", build_executor, source="test", is_factory=True)
    registry.declare_inject(
        "dsh",
        (InjectRequirement(service=ENVIRONMENT, capabilities=("exec", "upload")),),
    )
    graph = resolve(
        BindingIntent(profile_id="solver", environment="local", executor="dsh"),
        registry,
    )
    rows = graph.injects["dsh"]
    assert rows[0].service == "environment"
    assert set(rows[0].capabilities) == {"exec", "upload"}


@pytest.mark.asyncio
async def test_invoke_runs_worker_through_local_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGEVAL_OFFLINE_AGENT", "1")
    monkeypatch.setenv("litellm_api_key", "sk-not-for-argv")
    monkeypatch.setenv("litellm_base_url", "https://example.invalid/v1")
    host = SpyHost(tmp_path)
    await host.start()
    try:
        executor = build_executor(
            host=host,
            placement=host.placement(),
            model="deepseek-v4-flash",
            api_key="litellm_api_key",
            base_url="https://example.invalid/v1",
        )
        result = executor.invoke("count the rows", timeout=30)
    finally:
        await host.stop(delete=True)

    assert result.ok is False
    assert result.error == "offline_forced"
    assert result.metadata is not None
    assert result.metadata.get("execution_location") == "attempt-container"
    assert result.metadata.get("plugin") == "dsh"
    assert host.uploads, "worker files must be uploaded into the box"
    assert host.commands, "invoke must call host.exec"
    command, env = host.commands[0]
    assert command[0] == sys.executable
    request = json.loads(command[-1])
    assert "sk-not-for-argv" not in json.dumps(request)
    assert "api_key" not in request
    assert env is not None
    assert env.get("DEEPSEEK_API_KEY") == "sk-not-for-argv"
    assert env.get("DEEPSEEK_BASE_URL") == "https://example.invalid/v1"
    factory_src = (ROOT / "plugins" / "dsh" / "src" / "dsh_plugin" / "factory.py").read_text(
        encoding="utf-8"
    )
    container_src = (ROOT / "plugins" / "dsh" / "src" / "dsh_plugin" / "container.py").read_text(
        encoding="utf-8"
    )
    assert "import deepseek_harness" not in factory_src
    assert "from deepseek_harness" not in factory_src
    assert "import deepseek_harness" not in container_src
    assert "from deepseek_harness" not in container_src
