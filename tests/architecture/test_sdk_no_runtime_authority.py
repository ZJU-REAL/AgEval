"""Spec 06 architecture: bora_sdk must not own Runtime/credential/verdict authority."""

from __future__ import annotations

from pathlib import Path

SDK = Path(__file__).resolve().parents[2] / "sdk" / "python" / "src" / "bora_sdk"


def test_sdk_sources_do_not_import_runtime_authority() -> None:
    forbidden = (
        "bora.runtime",
        "bora.application",
        "bora.evaluation",
        "bora.provider",
        "bora.adapters",
        "bora.config",
    )
    for path in SDK.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert f"import {name}" not in text, f"{path} imports {name}"
            assert f"from {name}" not in text, f"{path} imports from {name}"
