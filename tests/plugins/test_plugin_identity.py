"""plugin_id identity: short in-repo ids, Hub org/name, path install cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.config.errors import ConfigError
from bora.plugins.manifest import (
    PluginManifestError,
    normalize_plugin_id,
    parse_manifest_mapping,
    require_namespaced_plugin_id,
    split_plugin_id,
)


def test_normalize_short_and_namespaced() -> None:
    assert normalize_plugin_id("nooa") == "nooa"
    assert normalize_plugin_id("sample-echo") == "sample-echo"
    assert normalize_plugin_id("acme/nooa") == "acme/nooa"
    assert normalize_plugin_id("Official/acp") == "Official/acp"
    assert normalize_plugin_id("Official/openai-http") == "Official/openai-http"
    assert split_plugin_id("acme/nooa") == ("acme", "nooa")
    assert split_plugin_id("dsh") == (None, "dsh")


@pytest.mark.parametrize(
    "raw",
    ["org.name", "acme//nooa", "acme/nooa/extra", "-bad", "acme/", "/nooa", ""],
)
def test_normalize_rejects_invalid(raw: str) -> None:
    with pytest.raises(PluginManifestError) as ei:
        normalize_plugin_id(raw)
    assert ei.value.kind in {"plugin_id_invalid", "plugin_manifest_invalid"}


def test_parse_manifest_keeps_namespaced_id() -> None:
    manifest = parse_manifest_mapping(
        {
            "format": "bora.plugin/1",
            "plugin_id": "acme/dsh",
            "version": "0.1.0",
            "slots": {"provide": [{"id": "executor", "entry": "pkg:fn"}]},
        }
    )
    assert manifest.plugin_id == "acme/dsh"


def test_hub_publish_requires_org_prefix() -> None:
    assert require_namespaced_plugin_id("test/sample-echo", org="test") == "test/sample-echo"
    with pytest.raises(PluginManifestError) as short:
        require_namespaced_plugin_id("sample-echo", org="test")
    assert short.value.kind == "plugin_id_not_namespaced"
    with pytest.raises(PluginManifestError) as mismatch:
        require_namespaced_plugin_id("other/sample-echo", org="test")
    assert mismatch.value.kind == "plugin_org_mismatch"


def test_publish_command_rejects_org_mismatch(tmp_path: Path) -> None:
    from bora.application.plugin_ops.plugin_publish import PluginPublishCommand

    root = tmp_path / "plug"
    root.mkdir()
    (root / "plugin.yaml").write_text(
        "format: bora.plugin/1\nplugin_id: acme/echo\nversion: 0.0.1\n",
        encoding="utf-8",
    )
    cmd = PluginPublishCommand(client_factory=lambda **_k: None)
    with pytest.raises(ConfigError) as ei:
        cmd.publish_plugin(root, org="other")
    assert ei.value.error_code == "plugin_org_mismatch"


def test_publish_command_rejects_short_plugin_id(tmp_path: Path) -> None:
    from bora.application.plugin_ops.plugin_publish import PluginPublishCommand

    root = tmp_path / "plug"
    root.mkdir()
    (root / "plugin.yaml").write_text(
        "format: bora.plugin/1\nplugin_id: sample-echo\nversion: 0.0.1\n",
        encoding="utf-8",
    )
    cmd = PluginPublishCommand(client_factory=lambda **_k: None)
    with pytest.raises(ConfigError) as ei:
        cmd.publish_plugin(root, org="test")
    assert ei.value.error_code == "plugin_id_not_namespaced"


def test_path_install_namespaced_id_and_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins.store import install_from_path, list_installed, uninstall

    src = tmp_path / "src"
    src.mkdir()
    (src / "plugin.yaml").write_text(
        "format: bora.plugin/1\nplugin_id: acme/echo\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (src / "readme.txt").write_text("hi\n", encoding="utf-8")
    entry = install_from_path(src)
    assert entry.plugin_id == "acme/echo"
    assert entry.version == "0.1.0"
    assert entry.digest.startswith("sha256:")
    assert (home / "plugins" / "acme" / "echo" / "0.1.0" / "plugin.yaml").is_file()
    assert list_installed()[0].plugin_id == "acme/echo"
    assert uninstall("acme/echo") is True
    assert list_installed() == []
    assert not (home / "plugins" / "acme").exists()
