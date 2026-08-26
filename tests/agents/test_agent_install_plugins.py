"""Agent install pulls declared plugins through one composition helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.application.agent_ops.install_plugins import (
    install_declared_plugins,
    plugin_ids_from_binding,
)
from ageval.config.errors import ConfigError


@pytest.fixture()
def ageval_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ageval-home"
    home.mkdir()
    monkeypatch.setenv("AGEVAL_HOME", str(home))
    from ageval.plugins import bootstrap as boot
    from ageval.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def _write_plugin(root: Path, plugin_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.yaml").write_text(
        (
            "format: ageval.plugin/1\n"
            f"plugin_id: {plugin_id.split('/')[-1]}\n"
            "version: 0.1.0\n"
            "slots:\n"
            "  chain:\n"
            "    - id: after_environment_ready\n"
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


def test_plugin_ids_from_binding_unique_order() -> None:
    assert plugin_ids_from_binding(
        {
            "extensions": [
                {"plugin": "dsh"},
                {"plugin": "acp"},
                {"plugin": "dsh"},
                {"options": {"entry": "pi"}},
            ]
        }
    ) == ["dsh", "acp"]


def test_contrib_plugin_is_skipped(ageval_home: Path) -> None:
    del ageval_home
    items = install_declared_plugins({"extensions": [{"plugin": "acp"}]})
    assert items == []


def test_hub_locator_uses_the_same_helper(ageval_home: Path, tmp_path: Path) -> None:
    del ageval_home
    extracted = _write_plugin(tmp_path / "extracted", "need-me")
    fetched: list[str] = []

    def hub_fetch(plugin_id: str) -> Path:
        fetched.append(plugin_id)
        return extracted

    items = install_declared_plugins(
        {"extensions": [{"plugin": "acme/need-me"}]},
        hub_fetch=hub_fetch,
    )
    assert fetched == ["acme/need-me"]
    assert items[0].plugin_id == "acme/need-me"
    assert items[0].status == "installed"

    again = install_declared_plugins(
        {"extensions": [{"plugin": "acme/need-me"}]},
        hub_fetch=hub_fetch,
    )
    assert again[0].status == "already_present"
    assert fetched == ["acme/need-me"]


def test_host_requires_message_names_import_and_hint(
    ageval_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del ageval_home
    plugin = tmp_path / "plugins" / "needs-host"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text(
        (
            "format: ageval.plugin/1\n"
            "plugin_id: needs-host\n"
            "version: 0.1.0\n"
            "host_requires:\n"
            "  - import: definitely_not_a_real_module\n"
            "    hint: uv sync --extra nooa\n"
            "slots:\n"
            "  chain:\n"
            "    - id: after_environment_ready\n"
            "      priority: 120\n"
            "      entry: demo.hooks:build\n"
        ),
        encoding="utf-8",
    )
    src = plugin / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "hooks.py").write_text(
        "def build(**_k):\n"
        "    async def h(ctx, value, nxt):\n"
        "        return await nxt(value)\n"
        "    return h\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as ei:
        install_declared_plugins({"extensions": [{"plugin": "needs-host"}]})
    assert ei.value.error_code == "host_requires_unsatisfied"
    assert "plugin cache" in ei.value.message
    assert "definitely_not_a_real_module" in ei.value.message
    assert "uv sync --extra nooa" in ei.value.message


def test_missing_plugin_fail_closes(ageval_home: Path) -> None:
    del ageval_home
    with pytest.raises(ConfigError) as ei:
        install_declared_plugins({"extensions": [{"plugin": "no-such-plugin"}]})
    assert ei.value.error_code == "plugin_requires_unsatisfied"


def test_path_and_registry_commands_share_helper() -> None:
    from ageval.application.agent_ops import install_remote as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert source.count("self._install_plugins(") >= 2
    assert "install_declared_plugins" in source
