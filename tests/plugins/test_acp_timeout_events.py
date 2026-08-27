"""Timeout keeps in-flight ACP rows so parent seal can fold them into trajectory."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.box import local_box

from ageval.environments.protocol import Placement
from ageval.plugins.contrib.acp.client import _AgevalAcpClient
from ageval.plugins.contrib.acp.executor import AcpExecutor

_TOOL = {
    "type": "session_update",
    "session_id": "s1",
    "update": {
        "sessionUpdate": "tool_call",
        "toolCallId": "c1",
        "title": "python variants.py",
        "kind": "execute",
    },
}


def _executor() -> AcpExecutor:
    return AcpExecutor(
        host=local_box("/nowhere"),
        placement=Placement(target_id="unstarted", home="/attempt/home"),
        entry_id="pi",
        model="entry-default",
    )


def _timeout_run(ex: AcpExecutor, client: _AgevalAcpClient, monkeypatch: object) -> None:
    monkeypatch.setattr(ex, "_ensure_session", lambda **_k: None)
    n = {"i": 0}

    def fake_run(coro: object, timeout: float = 0) -> object:
        del timeout
        getattr(coro, "close", lambda: None)()
        n["i"] += 1
        if n["i"] == 1:
            client.record(dict(_TOOL))
        raise TimeoutError

    monkeypatch.setattr(ex, "_run", fake_run)


def test_timeout_returns_mapped_tool_events(monkeypatch: object) -> None:
    ex = _executor()
    client = _AgevalAcpClient()
    ex._client = client
    _timeout_run(ex, client, monkeypatch)
    result = ex.invoke("hi", timeout=1)
    assert result.ok is False
    assert result.error == "acp_timeout"
    assert any(ev.get("kind") == "tool" for ev in result.events)
    assert any(ev.get("phase") == "timeout" for ev in result.events)


def test_timeout_writes_vendor_jsonl(monkeypatch: object, tmp_path: Path) -> None:
    ex = _executor()
    client = _AgevalAcpClient()
    ex._client = client
    _timeout_run(ex, client, monkeypatch)
    result = ex.invoke("hi", timeout=1, collect_dir=str(tmp_path))
    assert result.error == "acp_timeout"
    assert any(ev.get("kind") == "tool" for ev in result.events)
    vendor = (tmp_path / "acp_events.jsonl").read_text(encoding="utf-8")
    assert "tool_call" in vendor
    assert "c1" in vendor
