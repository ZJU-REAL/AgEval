"""v0.10 PostgreSQL environment adapter tests (Docker required)."""

from __future__ import annotations

import subprocess

import pytest

from bora.adapters.environment_postgres import new_postgres_environment


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def test_postgres_start_action_teardown() -> None:
    env = new_postgres_environment()
    try:
        env.start(timeout=90)
        denied = env.action("drop_all", {"sql": "SELECT 1"})
        assert denied["ok"] is False
        assert denied["error"] == "environment_action_denied"
        ok = env.action("query", {"sql": "SELECT 1"})
        assert ok["ok"] is True
        assert ok["stdout"].strip() == "1"
    finally:
        env.stop()


def test_action_limit() -> None:
    env = new_postgres_environment()
    env.action_limit = 1
    try:
        env.start(timeout=90)
        assert env.action("query", {"sql": "SELECT 1"})["ok"] is True
        second = env.action("query", {"sql": "SELECT 1"})
        assert second["ok"] is False
        assert second["error"] == "environment_action_limit_exceeded"
    finally:
        env.stop()
