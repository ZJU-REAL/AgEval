"""Host .env bootstrap does not override existing env; never returns secrets."""

from __future__ import annotations

import os
from pathlib import Path

from bora.application.env_bootstrap import apply_dotenv_file, load_host_env_files


def test_apply_dotenv_no_override(tmp_path: Path, monkeypatch: object) -> None:
    envf = tmp_path / ".env"
    envf.write_text("FOO_TEST_KEY=from_file\nBAR_TEST_KEY=bar\n", encoding="utf-8")
    monkeypatch.setenv("FOO_TEST_KEY", "from_process")  # type: ignore[attr-defined]
    monkeypatch.delenv("BAR_TEST_KEY", raising=False)  # type: ignore[attr-defined]
    n = apply_dotenv_file(envf, override=False)
    assert n >= 1
    assert os.environ["FOO_TEST_KEY"] == "from_process"
    assert os.environ["BAR_TEST_KEY"] == "bar"


def test_load_host_env_finds_repo_style_env(tmp_path: Path, monkeypatch: object) -> None:
    # Simulate package under a repo root with pyproject + src/bora and .env
    repo = tmp_path / "repo"
    (repo / "src" / "bora").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / ".env").write_text("BORA_TEST_LOCATOR=ok\n", encoding="utf-8")
    pkg = repo / "examples" / "pkg"
    pkg.mkdir(parents=True)
    monkeypatch.delenv("BORA_TEST_LOCATOR", raising=False)  # type: ignore[attr-defined]
    loaded = load_host_env_files(package_root=pkg)
    assert any(str(repo / ".env") == p or p.endswith(".env") for p in loaded)
    assert os.environ.get("BORA_TEST_LOCATOR") == "ok"
