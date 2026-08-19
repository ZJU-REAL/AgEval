"""Is the sidecar answering from inside the box? Write down what we found."""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

DEADLINE_SECONDS = 90


def main() -> None:
    error = "not attempted"
    deadline = time.monotonic() + DEADLINE_SECONDS
    finding: dict[str, object] = {}
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("db", 5432), timeout=3):
                finding = {"reachable": True, "service": "db", "port": 5432}
                break
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
    else:
        finding = {"reachable": False, "service": "db", "error": error}

    target = Path(os.environ["AGEVAL_WORKSPACE"]) / "db-probe.json"
    target.write_text(json.dumps(finding, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
