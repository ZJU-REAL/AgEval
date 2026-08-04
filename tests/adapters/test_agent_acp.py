"""Focused AcpExecutor unit tests (fixture-free mapping + offline)."""

from __future__ import annotations

import os

from bora.adapters.agent_acp import AcpExecutor
from bora.adapters.agent_contract import parse_validated_text_structured


def test_validated_text_structured_policy() -> None:
    assert parse_validated_text_structured('{"answer": 42}') == {"answer": 42}
    # Prose around JSON → no salvage
    assert parse_validated_text_structured('Here is {"answer": 42} done') is None
    assert parse_validated_text_structured("[1,2,3]") is None
    assert parse_validated_text_structured("") is None


def test_offline_forced() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        ex = AcpExecutor(entry_id="opencode", model="entry-default")
        r = ex.invoke("hi", timeout=5)
        assert r.ok is False
        assert r.error == "offline_forced"
        assert r.metadata is not None
        assert r.metadata.get("executor_kind") == "acp"
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


def test_unknown_entry_raises() -> None:
    try:
        AcpExecutor(entry_id="not-an-entry", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
