"""Shared audit log for slot-probe handlers (observable e2e evidence)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def probe_dir() -> Path:
    raw = (os.environ.get("BORA_SLOT_PROBE_DIR") or "").strip()
    if raw:
        p = Path(raw)
    else:
        p = Path.cwd() / ".bora_slot_probe"
    p.mkdir(parents=True, exist_ok=True)
    return p


def audit(slot: str, **fields: Any) -> None:
    """Append one JSON line to hooks.jsonl under BORA_SLOT_PROBE_DIR."""
    row = {
        "slot": slot,
        "ts": time.time(),
        "plugin": "slot-probe",
        **{k: v for k, v in fields.items() if v is not None},
    }
    path = probe_dir() / "hooks.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
