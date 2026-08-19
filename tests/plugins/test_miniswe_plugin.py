"""miniswe host SPI + docker-exec env (no live mini-swe-agent run)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[2] / "plugins" / "miniswe" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from miniswe_plugin.env import DockerExecEnv, build_docker_exec_argv  # noqa: E402
from miniswe_plugin.factory import (  # noqa: E402
    MinisweExecutorSPI,
    _load_official_mini_config,
    build_executor,
    describe_miniswe,
)
from miniswe_plugin.hooks import image_contribute, trajectory_collect  # noqa: E402
from miniswe_plugin.trajectory import SCHEMA, to_ageval_trajectory_events  # noqa: E402
def test_docker_exec_argv_uses_core_placement() -> None:
    argv = build_docker_exec_argv(
        container_id="abc",
        command="ls -la",
        uid=10001,
        gid=10001,
        workdir="/attempt/workspace",
    )
    assert argv[:3] == ["docker", "exec", "-u"]
    assert argv[3] == "10001:10001"
    assert argv[4:6] == ["-w", "/attempt/workspace"]
    assert argv[6] == "abc"
    assert argv[7:9] == ["bash", "-lc"]
    assert argv[9] == "ls -la"


def test_docker_env_never_starts_container() -> None:
    env = DockerExecEnv(
        container_id="already-running",
        uid=10001,
        gid=10001,
        workdir="/attempt/workspace",
    )
    assert env.container_id == "already-running"


def test_official_mini_yaml_loads() -> None:
    data = _load_official_mini_config()
    agent = data.get("agent") or {}
    assert agent.get("system_template")
    assert "{{task}}" in str(agent.get("instance_template") or "")


def test_invalid_step_limit() -> None:
    from ageval.plugins.errors import ExtensionMaterializeError

    with pytest.raises(ExtensionMaterializeError, match="step_limit"):
        build_executor(options={"step_limit": -1})


def test_offline_invoke_does_not_import_vendor(monkeypatch: object) -> None:
    monkeypatch.setenv("AGEVAL_OFFLINE_AGENT", "1")  # type: ignore[attr-defined]
    spi = MinisweExecutorSPI(model="openai/x", api_key="litellm_api_key")
    result = spi.invoke("ping")
    assert result.ok is False
    assert result.error == "offline_forced"


def test_messages_map_to_layer_b() -> None:
    mapped = to_ageval_trajectory_events(
        (
            {"role": "user", "content": "fix the bug"},
            {
                "role": "assistant",
                "content": "I will list files",
                "extra": {"actions": [{"command": "ls"}]},
            },
            {"role": "exit", "content": "Submitted", "extra": {"exit_status": "Submitted"}},
        )
    )
    assert all(e.get("schema") == SCHEMA for e in mapped)
    assert all(e.get("source") == "miniswe" for e in mapped)
    assert not any(e.get("type") == "session_update" for e in mapped)
    kinds = [e["kind"] for e in mapped]
    assert "text" in kinds
    assert "tool" in kinds
    tool = next(e for e in mapped if e["kind"] == "tool")
    assert tool["name"] == "bash"
    assert tool["arguments"]["command"] == "ls"


@pytest.mark.asyncio
async def test_image_contribute_declares_plugin() -> None:
    async def nxt(value: object) -> object:
        return value

    out = await image_contribute(None, [], nxt)
    assert out == [{"plugin": "miniswe"}]


@pytest.mark.asyncio
async def test_trajectory_collect_stamps_own_source() -> None:
    events = to_ageval_trajectory_events(({"role": "user", "content": "hi"},))

    async def nxt(value: object) -> object:
        return value

    out = await trajectory_collect(None, {"events": events, "metadata": {}}, nxt)
    assert out["metadata"]["trajectory_source"] == "miniswe"
