"""Spec 03: bora plugin install/list/uninstall/materialize + load into registry."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/plugins/sample-echo"


@pytest.fixture()
def bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    # Force re-bootstrap next ensure_bootstrapped with this home.
    from bora.plugins import bootstrap as boot

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    from bora.plugins.registry import reset_global_registry

    reset_global_registry()
    return home


def test_install_list_uninstall_atomic(bora_home: Path) -> None:
    from bora.plugins.paths import index_path, plugins_root
    from bora.plugins.store import install_from_path, list_installed, uninstall

    assert FIXTURE.is_dir()
    entry = install_from_path(FIXTURE)
    assert entry.plugin_id == "sample-echo"
    assert entry.digest.startswith("sha256:")
    assert (plugins_root() / entry.path / "plugin.yaml").is_file()
    assert index_path().is_file()
    idx = json.loads(index_path().read_text(encoding="utf-8"))
    assert any(p["plugin_id"] == "sample-echo" for p in idx["plugins"])

    # Idempotent reinstall
    entry2 = install_from_path(FIXTURE)
    assert entry2.digest == entry.digest
    assert len(list_installed()) == 1

    assert uninstall("sample-echo") is True
    assert list_installed() == []
    assert uninstall("sample-echo") is False


def test_bad_manifest_fail_closed(bora_home: Path, tmp_path: Path) -> None:
    from bora.plugins.manifest import PluginManifestError
    from bora.plugins.store import install_from_path

    bad = tmp_path / "bad-plugin"
    bad.mkdir()
    (bad / "plugin.yaml").write_text("format: not-a-plugin\n", encoding="utf-8")
    with pytest.raises(PluginManifestError) as ei:
        install_from_path(bad)
    assert ei.value.kind == "plugin_format_invalid"
    # No half install
    assert (
        not (bora_home / "plugins" / "index.json").exists()
        or list((bora_home / "plugins").glob("*/*")) == []
    )


def test_install_does_not_touch_profiles(bora_home: Path, tmp_path: Path) -> None:
    from bora.plugins.store import install_from_path

    project = tmp_path / "proj"
    project.mkdir()
    profiles = project / "profiles.yaml"
    original = "format: bora.profiles/1\nbindings: {}\n"
    profiles.write_text(original, encoding="utf-8")
    cwd = Path.cwd()
    try:
        os.chdir(project)
        install_from_path(FIXTURE)
    finally:
        os.chdir(cwd)
    assert profiles.read_text(encoding="utf-8") == original


def test_cli_install_list_json(bora_home: Path) -> None:
    env = {**os.environ, "BORA_HOME": str(bora_home)}
    proc = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "plugin", "install", str(FIXTURE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["plugin_id"] == "sample-echo"

    proc2 = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "plugin", "list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc2.returncode == 0
    listed = json.loads(proc2.stdout)
    assert any(p["plugin_id"] == "sample-echo" for p in listed["plugins"])


def test_load_installed_into_registry(bora_home: Path) -> None:
    from bora.plugins import bootstrap as boot
    from bora.plugins.bootstrap import bootstrap_registry
    from bora.plugins.protocol import BindingIntent
    from bora.plugins.registry import ExtensionRegistry, reset_global_registry
    from bora.plugins.resolve import resolve
    from bora.plugins.slots import EXECUTOR
    from bora.plugins.store import install_from_path

    install_from_path(FIXTURE)
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    reg = ExtensionRegistry()
    bootstrap_registry(reg)
    assert "sample-echo" in reg.plugins_for_slot(EXECUTOR)
    graph = resolve(
        BindingIntent(profile_id="s", executor="sample-echo"),
        reg,
        materialize=True,
    )
    assert graph.providers[EXECUTOR].plugin_id == "sample-echo"
    impl = graph.providers[EXECUTOR].impl
    assert getattr(impl, "kind", None) == "sample-echo"


def test_materialize_docs(bora_home: Path, tmp_path: Path) -> None:
    from bora.plugins.materialize import materialize_docs
    from bora.plugins.store import install_from_path

    install_from_path(FIXTURE)
    target = tmp_path / "docs-out"
    copied = materialize_docs("sample-echo", target)
    assert "README.md" in copied
    assert (target / "README.md").is_file()
    assert (target / "skills" / "echo" / "SKILL.md").is_file()


def test_recognition_discovers_sample_echo(bora_home: Path) -> None:
    from bora.adapters.agent_registry import discover_executor_kinds
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry
    from bora.plugins.store import install_from_path

    install_from_path(FIXTURE)
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    kinds = discover_executor_kinds()
    assert "sample-echo" in kinds
