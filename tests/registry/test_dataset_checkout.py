"""``checkout_dataset`` / ``ageval run --dir``: reuse local dest or fetch into it."""

from __future__ import annotations

import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler
from typer.testing import CliRunner

from ageval.application.composition import build_dataset_checkout, build_publish_command
from ageval.cli.main import app
from ageval.config.errors import ConfigError
from ageval.registry.client import RegistryClient, RegistryError
from ageval.registry.digest import compute_package_digest
from ageval.registry.resolve import checkout_dataset

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "datasets" / "publish-min"
TEST_ORG = "test"

publish_dataset = build_publish_command().publish_dataset


def _ensure_org() -> None:
    import os

    url = os.environ.get("AGEVAL_REGISTRY_URL") or ""
    token = os.environ.get("AGEVAL_REGISTRY_TOKEN") or ""
    if not url or not token:
        return
    client = RegistryClient(url, token=token)
    try:
        client.create_org(name=TEST_ORG, display_name="Test Org")
    except RegistryError:
        return


@pytest.fixture()
def registry_server(tmp_path: Path):
    data = tmp_path / "reg-data"
    state, token = build_default_state(data, bootstrap_token="test-token-publish", memory_blob=True)
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield {"url": f"http://127.0.0.1:{port}", "token": token, "state": state}
    server.shutdown()


def _child(parent: Path, dataset_id: str = "test/publish-min") -> Path:
    return parent.joinpath(*dataset_id.split("/"))


def test_checkout_reuses_matching_dest(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    dest = _child(parent)
    shutil.copytree(FIXTURE, dest)
    root = checkout_dataset("test/publish-min@0.1.0", parent)
    assert root == dest.resolve()
    assert (root / "ageval.yaml").is_file()


def test_checkout_rejects_local_path_positional(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    with pytest.raises(ConfigError) as ei:
        checkout_dataset(FIXTURE, parent)
    assert ei.value.error_code == "invalid_override"


def test_checkout_rejects_id_mismatch(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    dest = _child(parent)
    shutil.copytree(FIXTURE, dest)
    yaml = (dest / "ageval.yaml").read_text(encoding="utf-8")
    (dest / "ageval.yaml").write_text(
        yaml.replace("dataset_id: test/publish-min", "dataset_id: test/other"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        checkout_dataset("test/publish-min@0.1.0", parent)
    assert ei.value.error_code == "invalid_package"
    assert "test/other" in str(ei.value)


def test_checkout_rejects_version_mismatch(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    dest = _child(parent)
    shutil.copytree(FIXTURE, dest)
    yaml = (dest / "ageval.yaml").read_text(encoding="utf-8")
    (dest / "ageval.yaml").write_text(
        yaml.replace('version: "0.1.0"', 'version: "9.9.9"'),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        checkout_dataset("test/publish-min@0.1.0", parent)
    assert ei.value.error_code == "invalid_package"
    assert "9.9.9" in str(ei.value)


def test_checkout_rejects_occupied_non_dataset(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    dest = _child(parent)
    dest.mkdir(parents=True)
    (dest / "notes.txt").write_text("nope\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        checkout_dataset("test/publish-min@0.1.0", parent)
    assert ei.value.error_code == "invalid_package"


def test_checkout_rejects_file_dest(tmp_path: Path) -> None:
    parent = tmp_path / "tmp"
    parent.write_text("file\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        checkout_dataset("test/publish-min@0.1.0", parent)
    assert ei.value.error_code == "invalid_package"


def test_checkout_fetches_into_missing_dir(
    registry_server: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_URL", str(registry_server["url"]))
    monkeypatch.setenv("AGEVAL_REGISTRY_TOKEN", str(registry_server["token"]))
    monkeypatch.setenv("AGEVAL_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("HOME", str(tmp_path))
    _ensure_org()
    summary = publish_dataset(FIXTURE, public=False, org=TEST_ORG)
    parent = tmp_path / "nested"
    root = checkout_dataset(summary["ref"], parent)
    assert root == _child(parent).resolve()
    assert (root / "ageval.yaml").is_file()
    assert (root / "tasks" / "hello" / "task.yaml").is_file()
    assert not (root / ".ageval-verified").exists()
    again = checkout_dataset(summary["ref"], parent)
    assert again == root


def test_run_dir_installs_then_reuses_offline(
    registry_server: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_URL", str(registry_server["url"]))
    monkeypatch.setenv("AGEVAL_REGISTRY_TOKEN", str(registry_server["token"]))
    monkeypatch.setenv("AGEVAL_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _ensure_org()
    summary = publish_dataset(FIXTURE, public=False, org=TEST_ORG)

    runner = CliRunner()
    first = runner.invoke(
        app,
        ["run", summary["ref"], "--dir", "tmp", "--probe", "--task", "hello"],
    )
    dest = tmp_path / "tmp" / "test" / "publish-min"
    assert dest.is_dir(), first.output
    assert (dest / "ageval.yaml").is_file()
    assert compute_package_digest(dest) == summary["package_digest"]

    monkeypatch.delenv("AGEVAL_REGISTRY_URL", raising=False)
    monkeypatch.delenv("AGEVAL_REGISTRY_TOKEN", raising=False)
    second = runner.invoke(
        app,
        ["run", summary["ref"], "--dir", "tmp", "--probe", "--task", "hello"],
    )
    assert second.exit_code in {0, 2}, second.output
    assert (dest / "ageval.yaml").is_file()


def test_run_dir_with_local_path_is_one_error(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURE), "--dir", str(tmp_path / "demo"), "--probe", "--task", "hello"],
    )
    assert result.exit_code == 2
    assert "invalid_override" in (result.stderr or "")


def test_build_dataset_checkout_matches_module() -> None:
    assert build_dataset_checkout() is checkout_dataset
