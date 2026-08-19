"""Agent cache install/list/uninstall + pinned ref resolve (design/14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.agents import store
from bora.config.errors import ConfigError


@pytest.fixture(autouse=True)
def _bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    monkeypatch.setenv("BORA_HOME", str(home))
    return home


def _make_pkg(tmp_path: Path, agent_id: str = "mock-default", version: str = "0.1.0") -> Path:
    pkg = tmp_path / f"pkg-{agent_id}"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "agent.yaml").write_text(
        f"format: bora.agent/1\nagent_id: {agent_id}\nversion: '{version}'\n"
        "label: T\nbinding: {executor: mock, model: none}\n",
        encoding="utf-8",
    )
    return pkg


def test_install_list_resolve_roundtrip(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    entry = store.install_from_path(pkg)
    assert entry.agent_id == "local/mock-default"
    assert entry.version == "0.1.0"
    assert entry.digest.startswith("sha256:")

    rows = store.list_installed()
    assert [r.agent_id for r in rows] == ["local/mock-default"]

    got, root = store.resolve_installed_ref("local/mock-default", "0.1.0")
    assert got.digest == entry.digest
    assert (root / "agent.yaml").is_file()


def test_install_idempotent(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    a = store.install_from_path(pkg)
    b = store.install_from_path(pkg)
    assert a.digest == b.digest
    assert len(store.list_installed()) == 1


def test_hub_id_override(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    entry = store.install_from_path(pkg, agent_id="acme/mock-default")
    assert entry.agent_id == "acme/mock-default"
    _, root = store.resolve_installed_ref("acme/mock-default", "0.1.0")
    assert root.is_dir()


def test_resolve_missing_fails_closed() -> None:
    with pytest.raises(ConfigError):
        store.resolve_installed_ref("local/nope", "1.0")


def test_resolve_version_mismatch_fails_closed(tmp_path: Path) -> None:
    store.install_from_path(_make_pkg(tmp_path))
    with pytest.raises(ConfigError) as exc:
        store.resolve_installed_ref("local/mock-default", "9.9")
    assert "9.9" in str(exc.value)


def test_install_writes_overlay_files(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    skill = pkg / "overlays" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n", encoding="utf-8")
    (pkg / "agent.yaml").write_text(
        "format: bora.agent/1\nagent_id: mock-default\nversion: '0.1.0'\n"
        "label: T\nbinding:\n  executor: mock\n  model: none\n"
        "  overlays: [overlays/skills/demo]\n",
        encoding="utf-8",
    )
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    entry = store.install_from_path(pkg)
    root = store.resolve_package_root(entry)
    assert (root / "overlays" / "skills" / "demo" / "SKILL.md").is_file()
    assert not (dataset / "overlays").exists()


def test_uninstall(tmp_path: Path) -> None:
    store.install_from_path(_make_pkg(tmp_path))
    assert store.uninstall("local/mock-default") is True
    assert store.list_installed() == []
    assert store.uninstall("local/mock-default") is False
