"""Best-effort Vite spawn for bora view --dev (no real pnpm process)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bora.viewer.dev_ui import (
    fallback_commands,
    try_start_dev_ui,
    viewer_app_dir,
    vite_command,
)


def test_viewer_app_dir_finds_monorepo_app() -> None:
    app = viewer_app_dir()
    assert app is not None
    assert (app / "package.json").is_file()


def test_vite_command_does_not_insert_bare_dashdash() -> None:
    cmd = vite_command("/usr/bin/pnpm", host="127.0.0.1", port=5173)
    assert cmd[:3] == ["/usr/bin/pnpm", "exec", "vite"]
    assert "--" not in cmd
    assert "--port" in cmd
    assert "5173" in cmd


def test_fallback_commands_include_api_and_ui() -> None:
    a, b = fallback_commands(api_origin="http://127.0.0.1:8765", ui_port=5173)
    assert a == "VITE_VIEWER_API=http://127.0.0.1:8765 pnpm --dir apps/viewer dev"
    assert b == "open http://127.0.0.1:5173/"


def test_try_start_skipped_when_not_requested() -> None:
    result = try_start_dev_ui(
        api_origin="http://127.0.0.1:8765",
        ui_port=5173,
        start=False,
    )
    assert result.started is False
    assert result.reason == "skipped"
    assert result.proc is None


def test_try_start_reuses_listening_port() -> None:
    with patch("bora.viewer.dev_ui.port_listening", return_value=True):
        result = try_start_dev_ui(
            api_origin="http://127.0.0.1:8765",
            ui_port=5173,
            start=True,
        )
    assert result.started is True
    assert result.reused is True
    assert result.reason == "reused"
    assert result.proc is None


def test_try_start_no_app() -> None:
    with patch("bora.viewer.dev_ui.viewer_app_dir", return_value=None):
        result = try_start_dev_ui(
            api_origin="http://127.0.0.1:8765",
            ui_port=5173,
            start=True,
        )
    assert result.started is False
    assert result.reason == "no_app"


def test_try_start_no_pnpm(tmp_path: Path) -> None:
    app = tmp_path / "viewer"
    app.mkdir()
    (app / "package.json").write_text("{}\n", encoding="utf-8")
    (app / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")
    (app / "node_modules").mkdir()
    with (
        patch("bora.viewer.dev_ui.viewer_app_dir", return_value=app),
        patch("bora.viewer.dev_ui.port_listening", return_value=False),
        patch("bora.viewer.dev_ui.shutil.which", return_value=None),
    ):
        result = try_start_dev_ui(
            api_origin="http://127.0.0.1:8765",
            ui_port=5173,
            start=True,
        )
    assert result.started is False
    assert result.reason == "no_pnpm"


def test_try_start_no_modules(tmp_path: Path) -> None:
    app = tmp_path / "viewer"
    app.mkdir()
    (app / "package.json").write_text("{}\n", encoding="utf-8")
    (app / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")
    with (
        patch("bora.viewer.dev_ui.viewer_app_dir", return_value=app),
        patch("bora.viewer.dev_ui.port_listening", return_value=False),
        patch("bora.viewer.dev_ui.shutil.which", return_value="/usr/bin/pnpm"),
    ):
        result = try_start_dev_ui(
            api_origin="http://127.0.0.1:8765",
            ui_port=5173,
            start=True,
        )
    assert result.started is False
    assert result.reason == "no_modules"
