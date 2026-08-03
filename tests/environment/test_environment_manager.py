"""Environment Manager unit tests."""

from __future__ import annotations

import subprocess

import pytest

from bora.environment.manager import EnvironmentManager


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"], check=False, capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def test_manager_open_action_close() -> None:
    mgr = EnvironmentManager(attempt_id="attempt_test", action_limit=5)
    try:
        opened = mgr.open_resource("postgresql")
        assert opened["ok"] is True
        rid = opened["resource_id"]
        q = mgr.action(rid, "query", {"sql": "SELECT 1"})
        assert q["ok"] is True
        denied = mgr.action(rid, "drop_all", {"sql": "SELECT 1"})
        assert denied["ok"] is False
    finally:
        mgr.close()
    assert mgr.closed is True
    assert mgr.action("x", "query", {})["error"] == "environment_closed"


def test_unknown_kind() -> None:
    mgr = EnvironmentManager(attempt_id="a")
    bad = mgr.open_resource("mysql")
    assert bad["ok"] is False
    assert bad["error"] == "unknown_resource_kind"
