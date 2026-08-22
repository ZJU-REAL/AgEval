"""ACP source probe: offline refuses cleanly before touching the box."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.helpers.box import local_box

from ageval.environments.protocol import Placement
from ageval.plugins.agent_result import parse_validated_text_structured
from ageval.plugins.contrib.acp import AcpExecutor


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
