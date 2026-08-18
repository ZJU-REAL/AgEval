"""Transitive plugin install: sibling vs Hub org/name, cycles, no partial row."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bora.plugins.install import install_extracted_hub, install_from_local
from bora.plugins.plugin_requires import PluginRequiresError
from bora.plugins.store import list_installed, uninstall

ROOT = Path(__file__).resolve().parents[2]


def _write_plugin(root: Path, plugin_id: str, *, requires: list[str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = ""
    if requires:
        req_yaml = "\n".join(f"  - plugin_id: {pid}" for pid in requires)
        rows = f"plugin_requires:\n{req_yaml}\n"
    (root / "plugin.yaml").write_text(
        (
            "format: bora.plugin/1\n"
            f"plugin_id: {plugin_id}\n"
            "version: 0.1.0\n"
            f"{rows}"
            "slots:\n"
            '  "on":\n'
            "    - id: home_overlay\n"
            "      priority: 120\n"
            "      entry: demo.hooks:build\n"
        ),
        encoding="utf-8",
    )
    src = root / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "hooks.py").write_text(
        "def build(**_k):\n"
        "    async def h(ctx, value, nxt):\n"
        "        return await nxt(value)\n"
        "    return h\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def test_local_sibling_installs_both(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "home-files", "home-files")
    _write_plugin(plugins / "agent-skills", "agent-skills", requires=["home-files"])
    result = install_from_local(plugins / "agent-skills")
    ids = {e.plugin_id for e in list_installed()}
    assert ids == {"agent-skills", "home-files"}
    statuses = {item.plugin_id: item.status for item in result.items}
    assert statuses["home-files"] == "installed"
    assert statuses["agent-skills"] == "installed"
    again = install_from_local(plugins / "agent-skills")
    assert all(item.status == "already_present" for item in again.items)


def test_short_id_missing_sibling_no_partial_row(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "agent-skills", "agent-skills", requires=["home-files"])
    fetched: list[str] = []

    def hub_fetch(package_id: str) -> Path:
        fetched.append(package_id)
        raise AssertionError(f"short id must not hit Hub: {package_id}")

    with pytest.raises(PluginRequiresError) as ei:
        install_from_local(plugins / "agent-skills", hub_fetch=hub_fetch)
    assert ei.value.kind == "plugin_requires_unsatisfied"
    assert fetched == []
    assert list_installed() == []


def test_hub_dep_uses_declared_org_not_parent(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    parent = _write_plugin(tmp_path / "a", "a", requires=["OrgB/b"])
    dep = _write_plugin(tmp_path / "b", "b")
    fetched: list[str] = []

    def hub_fetch(package_id: str) -> Path:
        fetched.append(package_id)
        assert package_id == "OrgB/b"
        return dep

    result = install_extracted_hub(parent, plugin_id="OrgA/a", hub_fetch=hub_fetch)
    assert fetched == ["OrgB/b"]
    ids = {e.plugin_id for e in list_installed()}
    assert ids == {"OrgA/a", "OrgB/b"}
    assert result.entry.plugin_id == "OrgA/a"


def test_hub_parent_short_dep_does_not_guess_org(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    parent = _write_plugin(tmp_path / "a", "a", requires=["b"])
    fetched: list[str] = []

    def hub_fetch(package_id: str) -> Path:
        fetched.append(package_id)
        raise AssertionError("must not fetch OrgA/b")

    with pytest.raises(PluginRequiresError) as ei:
        install_extracted_hub(parent, plugin_id="OrgA/a", hub_fetch=hub_fetch)
    assert ei.value.kind == "plugin_requires_unsatisfied"
    assert fetched == []
    assert list_installed() == []


def test_cycle_fail_closed(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "alpha", "alpha", requires=["beta"])
    _write_plugin(plugins / "beta", "beta", requires=["alpha"])
    with pytest.raises(PluginRequiresError) as ei:
        install_from_local(plugins / "alpha")
    assert ei.value.kind == "plugin_requires_cycle"
    assert list_installed() == []


def test_uninstall_depender_leaves_dep(bora_home: Path, tmp_path: Path) -> None:
    del bora_home
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "home-files", "home-files")
    _write_plugin(plugins / "agent-skills", "agent-skills", requires=["home-files"])
    install_from_local(plugins / "agent-skills")
    assert uninstall("agent-skills") is True
    ids = {e.plugin_id for e in list_installed()}
    assert ids == {"home-files"}


def test_cli_install_sibling_json(bora_home: Path, tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "home-files", "home-files")
    _write_plugin(plugins / "agent-skills", "agent-skills", requires=["home-files"])
    env = {**os.environ, "BORA_HOME": str(bora_home)}
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "plugin", "install", str(plugins / "agent-skills")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["plugin_id"] == "agent-skills"
    listed_ids = {row["plugin_id"] for row in data["installed"]}
    assert listed_ids == {"agent-skills", "home-files"}
