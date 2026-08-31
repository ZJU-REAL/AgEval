"""Single-distribution architecture: ageval_sdk must not import ageval.

The SDK ships in the same wheel (distribution ``ageval-cli``, two top-level
packages); this import boundary replaces the old separate-package graph
isolation and keeps SDK ownership limited to task-author-facing types.
"""

from __future__ import annotations

import re
from pathlib import Path

SDK = Path(__file__).resolve().parents[2] / "src" / "ageval_sdk"

AGEVAL_IMPORT = re.compile(r"^\s*(?:from|import)\s+ageval(?:\.|\s|$)", re.MULTILINE)


def test_sdk_sources_do_not_import_ageval() -> None:
    for path in SDK.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        match = AGEVAL_IMPORT.search(text)
        assert match is None, f"{path} imports ageval: {match.group(0) if match else ''!r}"
