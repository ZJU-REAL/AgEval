"""plugin_requires allowlist on ageval.plugin/1."""

from __future__ import annotations

import pytest

from ageval.plugins.manifest import PluginManifestError, parse_manifest_mapping


def _base(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "ageval.plugin/1",
        "plugin_id": "demo",
        "version": "0.1.0",
        "slots": {"on": [{"id": "home_overlay", "priority": 120, "entry": "demo.hooks:build"}]},
    }
    payload.update(extra)
    return payload


def test_plugin_requires_short_and_hub_ids() -> None:
    man = parse_manifest_mapping(
        _base(
            plugin_requires=[
                {"plugin_id": "home-files", "hint": "ageval plugin install plugins/home-files"},
                {"plugin_id": "Official/home-files"},
            ]
        )
    )
    assert len(man.plugin_requires) == 2
    assert man.plugin_requires[0].plugin_id == "home-files"
    assert man.plugin_requires[0].hint == "ageval plugin install plugins/home-files"
    assert man.plugin_requires[1].plugin_id == "Official/home-files"
    assert man.plugin_requires[1].hint is None


def test_omitted_and_empty_plugin_requires() -> None:
    assert parse_manifest_mapping(_base()).plugin_requires == ()
    assert parse_manifest_mapping(_base(plugin_requires=[])).plugin_requires == ()


def test_unknown_plugin_requires_key_fail_closed() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(plugin_requires=[{"plugin_id": "home-files", "version": "1"}]))
    assert ei.value.kind == "plugin_requires_invalid"
    assert "unknown keys" in str(ei.value)


def test_invalid_plugin_id_fail_closed() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(plugin_requires=[{"plugin_id": "org.name"}]))
    assert ei.value.kind == "plugin_requires_invalid"


def test_plugin_requires_not_a_list() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(plugin_requires={"plugin_id": "home-files"}))
    assert ei.value.kind == "plugin_requires_invalid"


def test_plugin_requires_missing_id() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(plugin_requires=[{"hint": "only hint"}]))
    assert ei.value.kind == "plugin_requires_invalid"
