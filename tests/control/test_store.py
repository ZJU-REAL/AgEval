"""v0.12 control store tests."""

from __future__ import annotations

from pathlib import Path

from bora.control.store import ControlStore


def test_put_get_version(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    v1 = store.put("run_a", status="running", owner="local", payload={"x": 1})
    v2 = store.put("run_a", status="terminal", owner="local", payload={"x": 2})
    assert v1 == 1
    assert v2 == 2
    got = store.get("run_a")
    assert got is not None
    assert got["status"] == "terminal"
    assert got["version"] == 2
    assert store.get("missing") is None
