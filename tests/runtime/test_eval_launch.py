"""Eval worker parent serve loop: drain stderr while waiting for frames."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from ageval.runtime.task_launch import _STDERR_TAIL_BYTES, _serve_eval_worker

_FLOOD_SCRIPT = r"""
import json, struct, sys
sys.stderr.write("x" * 80000)
sys.stderr.flush()
raw = json.dumps({"ok": True, "verdict": {"status": "PASS", "score": 1.0}}).encode()
sys.stdout.buffer.write(struct.pack("!I", len(raw)) + raw)
sys.stdout.buffer.flush()
sys.stdin.read()
"""


@pytest.mark.asyncio
async def test_serve_eval_worker_drains_stderr_before_verdict() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _FLOOD_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    ctx = SimpleNamespace()
    envelope = await asyncio.wait_for(_serve_eval_worker(process, ctx, timeout=5.0), timeout=6.0)
    assert envelope.get("ok") is True
    assert envelope.get("verdict") == {"status": "PASS", "score": 1.0}
    stderr = str(envelope.get("stderr") or "")
    assert stderr.endswith("x" * min(80000, _STDERR_TAIL_BYTES))
    assert len(stderr) <= _STDERR_TAIL_BYTES
