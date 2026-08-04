"""Real process-group feasibility probe (POSIX)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "helpers" / "provider_probe_child.py"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups only")
def test_term_kill_escalation(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.txt"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(HELPER),
            "--mode",
            "ignore-term",
            "--path",
            str(sentinel),
            "--seconds",
            "5",
        ],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pgid = os.getpgid(proc.pid)
    time.sleep(0.2)
    os.killpg(pgid, signal.SIGTERM)
    time.sleep(0.2)
    # Still alive because it ignores TERM
    alive_after_term = True
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        alive_after_term = False
    assert alive_after_term
    os.killpg(pgid, signal.SIGKILL)
    proc.wait(timeout=2)
    time.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)
