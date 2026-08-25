"""Drop layer A/B vendor raw after a successful trajectory seal.

Layout strings live here. Observational — never PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_INVOCATION_DROP = frozenset(
    {
        "request.json",
        "events.jsonl",
        "final-response.json",
        "metadata.json",
        "stderr.txt",
        "trajectory.jsonl",
    }
)


def is_vendor_raw_rel(rel: str) -> bool:
    """True when *rel* (posix, run-dir relative) is invoke scratch / vendor raw."""
    parts = Path(rel).parts
    if "backend_raw" in parts:
        return True
    if rel == "agent/events.jsonl":
        return True
    if rel == "evaluation/evaluator_raw.json":
        return True
    return (
        len(parts) >= 4
        and parts[0] == "agent"
        and parts[1] == "invocations"
        and parts[-1] in _INVOCATION_DROP
    )


def slim_sealed_attempt(run_dir: Path) -> None:
    """Delete vendor raw / layer B after layer C exists. Keep invocation dirs."""
    root = run_dir
    events = root / "agent" / "events.jsonl"
    if events.is_file():
        events.unlink()
    raw_eval = root / "evaluation" / "evaluator_raw.json"
    if raw_eval.is_file():
        raw_eval.unlink()
    inv_root = root / "agent" / "invocations"
    if not inv_root.is_dir():
        return
    for inv in inv_root.iterdir():
        if not inv.is_dir():
            continue
        backend = inv / "backend_raw"
        if backend.is_dir():
            shutil.rmtree(backend)
        elif backend.is_file():
            backend.unlink()
        for name in _INVOCATION_DROP:
            path = inv / name
            if path.is_file():
                path.unlink()
