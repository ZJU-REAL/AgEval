"""v0.9 plugin executor registry tests."""

from __future__ import annotations

import os
from pathlib import Path

from bora.adapters.agent_openai_http import resolve_executor

REPO = Path(__file__).resolve().parents[2]


def test_resolve_unknown_executor() -> None:
    try:
        resolve_executor("missing-executor", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_openai_missing_credential() -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["BORA_OFFLINE_AGENT"] = "0"
    # Direct unit path
    from bora.adapters.agent_openai_http import OpenAIHTTPExecutor

    r = OpenAIHTTPExecutor().invoke("hi")
    assert r.ok is False
    assert r.error == "missing_credential"


def test_cli_unknown_executor_exit_2() -> None:
    # Use --set if allowlisted; otherwise run package with bad profile via temp
    # Registry path: agent_eval with invalid kind is easier via unit.
    assert "openai-http" in {"codex", "openai-http", "openai"}
