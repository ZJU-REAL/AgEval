"""bora.agent/1 manifest parse + fail-closed secret scan (design/14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.agents.manifest import AGENT_FILENAME, load_agent_manifest, parse_agent_document
from bora.config.errors import ConfigError

GOOD_DOC = {
    "format": "bora.agent/1",
    "agent_id": "mock-default",
    "version": "0.1.0",
    "label": "Mock Default",
    "tags": ["ci"],
    "binding": {
        "executor": "mock",
        "model": "none",
    },
}


def _write_pkg(root: Path, doc_text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / AGENT_FILENAME).write_text(doc_text, encoding="utf-8")
    return root


def test_parse_good_document() -> None:
    m = parse_agent_document(dict(GOOD_DOC))
    assert m.agent_id == "mock-default"
    assert m.version == "0.1.0"
    assert m.binding["executor"] == "mock"
    # label sinks into binding.label when binding omits it
    assert m.binding["label"] == "Mock Default"
    assert m.tags == ("ci",)


def test_unknown_top_key_fails() -> None:
    doc = dict(GOOD_DOC)
    doc["skills"] = ["x"]
    with pytest.raises(ConfigError):
        parse_agent_document(doc)


def test_bad_format_fails() -> None:
    doc = dict(GOOD_DOC)
    doc["format"] = "bora.agent/2"
    with pytest.raises(ConfigError):
        parse_agent_document(doc)


def test_reserved_agent_ref_rejected() -> None:
    doc = dict(GOOD_DOC)
    doc["binding"] = {"executor": "mock", "model": "none", "agent_ref": "x@1"}
    with pytest.raises(ConfigError) as exc:
        parse_agent_document(doc)
    assert "agent_ref" in str(exc.value)


def test_unknown_binding_key_rejected() -> None:
    doc = dict(GOOD_DOC)
    doc["binding"] = {"executor": "mock", "model": "none", "token": "sk-nope"}
    with pytest.raises(ConfigError):
        parse_agent_document(doc)


def test_load_from_dir_and_bare_yaml(tmp_path: Path) -> None:
    pkg = _write_pkg(
        tmp_path / "agent-pkg",
        "format: bora.agent/1\nagent_id: a1\nversion: '1.0'\n"
        "binding: {executor: mock, model: none}\n",
    )
    m = load_agent_manifest(pkg)
    assert m.root == pkg
    m2 = load_agent_manifest(pkg / AGENT_FILENAME)
    assert m2.root is None
    assert m2.agent_id == "a1"


def test_secret_in_package_fails_closed(tmp_path: Path) -> None:
    pkg = _write_pkg(
        tmp_path / "leaky",
        "format: bora.agent/1\nagent_id: leaky\nversion: '1.0'\n"
        "binding: {executor: mock, model: none}\n",
    )
    (pkg / "notes.txt").write_text("api_key = sk-abc123def456ghi789jkl000\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_agent_manifest(pkg)


def test_locator_name_is_clean(tmp_path: Path) -> None:
    pkg = _write_pkg(
        tmp_path / "locator",
        "format: bora.agent/1\nagent_id: locator\nversion: '1.0'\n"
        "binding: {executor: mock, model: none, api_key: '${OPENAI_API_KEY}'}\n",
    )
    m = load_agent_manifest(pkg)
    assert m.binding["api_key"] == "${OPENAI_API_KEY}"
