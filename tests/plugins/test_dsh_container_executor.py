"""dsh container SPI + host factory (no live DeepSeek runtime)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from bora.runtime.identity import IdentityFactory

_DSH_SRC = Path(__file__).resolve().parents[2] / "plugins" / "dsh" / "src"
if str(_DSH_SRC) not in sys.path:
    sys.path.insert(0, str(_DSH_SRC))

from dsh_plugin.container import DshContainerExecutor  # noqa: E402
from dsh_plugin.factory import DshExecutorSPI, build_executor, describe_dsh  # noqa: E402
from dsh_plugin.hooks import image_contribute, trajectory_collect  # noqa: E402
from dsh_plugin.trajectory import SCHEMA  # noqa: E402


def test_describe_and_bind_to_target() -> None:
    desc = describe_dsh()
    assert desc["binary"] == "dsh-jsonrpc-agent"
    assert "DEEPSEEK_API_KEY" in desc["credential_env_names"]
    spi = build_executor(
        options={"composition": "slim"},
        model="deepseek-v4-flash",
        api_key="deepseek_api_key",
        profile_id="solver",
    )
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
    assert bound.execution_location == "attempt-container"
    assert bound.model == "deepseek-v4-flash"


def test_offline_invoke_does_not_start(monkeypatch: object) -> None:
    monkeypatch.setenv("BORA_OFFLINE_AGENT", "1")  # type: ignore[attr-defined]
    spi = DshExecutorSPI(model="deepseek-v4-flash", api_key="deepseek_api_key")
    result = spi.invoke("ping")
    assert result.ok is False
    assert result.error == "offline_forced"


def test_container_executor_parses_worker_stdout() -> None:
    payload = {
        "model": "deepseek-v4-flash",
        "text": '{"status":"completed"}',
        "structured": {"status": "completed"},
        "ok": True,
        "error": None,
        "events": [
            {
                "schema": SCHEMA,
                "seq": 1,
                "session_id": "s",
                "source": "dsh",
                "kind": "text",
                "channel": "assistant",
                "text": "ok",
            }
        ],
        "native_events": [{"type": "turn/end", "data": {"reason": {"kind": "completed"}}}],
        "metadata": {"plugin": "dsh", "execution_location": "attempt-container"},
    }

    def fake_supervise(argv, **kwargs):  # noqa: ANN001, ANN003
        del argv, kwargs
        factory = IdentityFactory()
        attempt = factory.new_attempt(factory.new_trial(factory.new_run(), "sha256:" + "d" * 64))
        return ProcessOutcome(
            attempt=attempt,
            assurance="l0",
            terminal=ProcessTerminalKind.EXITED,
            exit_code=0,
            signal=None,
            stdout_summary=json.dumps(payload) + "\n",
            stderr_summary="",
            truncated=False,
            pid=None,
            pgid=None,
            writer_stop_confirmed=True,
            cleanup_ok=True,
        )

    ex = DshContainerExecutor(container_id="cid123", model="deepseek-v4-flash")
    with patch("dsh_plugin.container.supervise_docker_cli", side_effect=fake_supervise):
        result = ex.invoke("do it", timeout=5.0)
    assert result.ok
    assert result.metadata is not None
    assert result.metadata.get("execution_location") == "attempt-container"
    assert result.metadata.get("plugin") == "dsh"
    assert result.events[0]["source"] == "dsh"


async def test_image_contribute_declares_plugin() -> None:
    async def nxt(value: object) -> object:
        return value

    out = await image_contribute(None, [], nxt)
    assert out == [{"plugin": "dsh"}]


async def test_trajectory_collect_maps_native() -> None:
    async def nxt(value: object) -> object:
        return value

    native = {
        "events": (
            {
                "type": "tool/call",
                "data": {"callId": "c", "name": "bash", "arguments": '{"command":"ls"}'},
            },
        )
    }
    out = await trajectory_collect(None, native, nxt)
    assert out["metadata"]["trajectory_source"] == "dsh"
    assert out["events"][0]["schema"] == SCHEMA
    assert out["events"][0]["source"] == "dsh"
