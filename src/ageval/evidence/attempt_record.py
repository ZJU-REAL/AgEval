"""Attempt record layout owned by evidence — result.json and run-dir inference.

Writers and readers must use these helpers so layout strings are not copied.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ageval.evidence.redaction import redact_and_assert

RESULT_FILENAME = "result.json"
AGENT_FILENAME = "agent.json"
HARNESS_FILENAME = "harness.json"
L1_FILENAME = "l1.json"


def infer_database_root_from_run_dir(run_dir: Path | str) -> Path | None:
    """Infer Database root when *run_dir* is ``…/.ageval/runs/<run_id>``."""
    p = Path(run_dir).resolve(strict=False)
    if p.parent.name == "runs" and p.parent.parent.name == ".ageval":
        return p.parent.parent.parent
    return None


def result_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / RESULT_FILENAME


def write_attempt_result(run_dir: Path | str, doc: dict[str, Any]) -> Path:
    """Atomically write sealed ``result.json`` under the Attempt run directory."""
    path = result_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    raw = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n"
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_attempt_result(run_dir: Path | str) -> dict[str, Any] | None:
    """Read ``result.json`` when present and parseable as an object."""
    path = result_path(run_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_attempt_json(
    run_dir: Path | str,
    filename: str,
    doc: dict[str, Any],
    *,
    redact: bool = False,
) -> Path:
    """Write a sibling Attempt JSON document (agent/harness/l1).

    When *redact* is true, run fail-closed redaction before seal (no string replace).
    """
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("filename must be a single path segment")
    payload: Any = doc
    if redact:
        payload = redact_and_assert(doc)
    path = Path(run_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    raw = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n"
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)
    return path


def has_attempt_result(run_dir: Path | str) -> bool:
    return result_path(run_dir).is_file()
