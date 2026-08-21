"""ACP source probe: offline refuses cleanly; a real entry produces real events."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest
from tests.helpers.box import local_box

from ageval.environments.protocol import Placement
from ageval.plugins.agent_result import parse_validated_text_structured
from ageval.plugins.contrib.acp import AcpExecutor

REAL_ENTRY = "pi"


def test_validated_text_no_regex_salvage() -> None:
    assert parse_validated_text_structured('{"answer": 1}') == {"answer": 1}
    assert parse_validated_text_structured('prefix {"answer": 1}') is None


def test_offline_refuses_before_touching_the_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGEVAL_OFFLINE_AGENT", "1")
    executor = AcpExecutor(
        entry_id="opencode",
        host=local_box(tmp_path / "box"),
        placement=Placement(target_id="unstarted"),
    )
    result = executor.invoke("hi")

    assert result.ok is False
    assert result.error == "offline_forced"
    assert any(event.get("type") == "lifecycle" for event in result.events)
    assert result.metadata is not None
    assert result.metadata.get("executor_kind") == "acp"


@pytest.mark.skipif(
    os.environ.get("AGEVAL_SKIP_REAL_ACP") == "1",
    reason="explicit skip real ACP probe",
)
def test_a_real_entry_answers_over_the_attached_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which(REAL_ENTRY) is None:
        pytest.skip(f"{REAL_ENTRY} not on PATH")
    monkeypatch.delenv("AGEVAL_OFFLINE_AGENT", raising=False)

    host = local_box(tmp_path / "box")
    asyncio.run(host.preflight())
    asyncio.run(host.start())
    executor = AcpExecutor(entry_id=REAL_ENTRY, host=host, placement=host.placement())
    try:
        result = executor.invoke('Reply with ONLY JSON {"ok": true} and nothing else.', timeout=180)
    finally:
        executor.close()
        asyncio.run(host.stop(delete=True))

    assert result.metadata is not None
    assert result.metadata["acp_entry_id"] == REAL_ENTRY
    assert result.events, "a real session must leave a trajectory"
