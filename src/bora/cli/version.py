"""CLI package version helpers."""

from __future__ import annotations

from pathlib import Path

import typer


def package_version() -> str:
    """Installed package version, with repo ``VERSION`` file as fallback."""
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("bora")
    except Exception:  # noqa: BLE001 — offline / editable edge cases
        version_file = Path(__file__).resolve().parents[3] / "VERSION"
        if version_file.is_file():
            text = version_file.read_text(encoding="utf-8").strip()
            if text:
                return text
        return "0.0.0+unknown"


def version_callback(value: bool) -> None:
    if value:
        typer.echo(package_version())
        raise typer.Exit(0)
