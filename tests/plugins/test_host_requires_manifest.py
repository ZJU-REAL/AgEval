"""host_requires allowlist on ageval.plugin/1."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ageval.plugins.manifest import PluginManifestError, parse_manifest_mapping


def _base(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "ageval.plugin/1",
        "plugin_id": "demo",
        "version": "0.1.0",
        "slots": {
            "provide": [{"id": "executor", "priority": 10, "entry": "demo.factory:build_executor"}]
        },
    }
    payload.update(extra)
    return payload


def test_host_requires_import_and_file() -> None:
    man = parse_manifest_mapping(
        _base(
            host_requires=[
                {"import": "json", "hint": "stdlib"},
                {"file": "compositions/default.yml"},
            ]
        )
    )
    assert len(man.host_requires) == 2
    assert man.host_requires[0].import_name == "json"
    assert man.host_requires[0].hint == "stdlib"
    assert man.host_requires[1].file == "compositions/default.yml"


def test_unknown_host_requires_key_fail_closed() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(host_requires=[{"import": "json", "pip_extra": "dsh"}]))
    assert ei.value.kind == "plugin_host_requires_invalid"
    assert "unknown keys" in str(ei.value)


def test_host_requires_must_declare_import_or_file() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(host_requires=[{"hint": "only hint"}]))
    assert ei.value.kind == "plugin_host_requires_invalid"


def test_host_requires_not_a_list() -> None:
    with pytest.raises(PluginManifestError) as ei:
        parse_manifest_mapping(_base(host_requires={"import": "json"}))
    assert ei.value.kind == "plugin_host_requires_invalid"


def test_fixture_plugin_yaml_parses(tmp_path: Path) -> None:
    del tmp_path
    root = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "host-probe"
    raw = yaml.safe_load((root / "plugin.yaml").read_text(encoding="utf-8"))
    man = parse_manifest_mapping(raw, location=str(root / "plugin.yaml"))
    assert man.plugin_id == "host-probe"
    assert man.host_requires[0].import_name == "host_probe_vendor_sdk"
