"""Spec 04: publish plugin → preview → install to local cache."""

from __future__ import annotations

import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler

from bora.application.composition import build_plugin_commands
from bora.registry.client import RegistryClient
from bora.registry.credentials import write_credentials
from bora.registry.plugin_package import PLUGIN_MEDIA_TYPE

_plugins = build_plugin_commands()
install_plugin_from_registry = _plugins.install_plugin_from_registry
publish_plugin = _plugins.publish_plugin

REPO = Path(__file__).resolve().parents[2]
PLUGIN_FIXTURE = REPO / "tests" / "fixtures" / "plugins" / "sample-echo"
TEST_ORG = "test"


@pytest.fixture()
def registry_server(tmp_path: Path):
    data = tmp_path / "reg-data"
    state, token = build_default_state(data, bootstrap_token="test-token-plugin", memory_blob=True)
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    yield {"url": url, "token": token, "state": state}
    server.shutdown()


def _ensure_org(url: str, token: str) -> None:
    client = RegistryClient(url, token=token)
    try:
        client.create_org(name=TEST_ORG, display_name="Test Org")
    except Exception:
        return


def test_publish_plugin_preview_and_install(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds = tmp_path / "credentials"
    write_credentials(
        url=registry_server["url"],
        token=registry_server["token"],
        path=creds,
    )
    monkeypatch.setenv("BORA_REGISTRY_URL", registry_server["url"])
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", registry_server["token"])
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()

    _ensure_org(registry_server["url"], registry_server["token"])

    namespaced = tmp_path / "sample-echo"
    shutil.copytree(PLUGIN_FIXTURE, namespaced)
    yaml_path = namespaced / "plugin.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").replace(
            "plugin_id: sample-echo",
            f"plugin_id: {TEST_ORG}/sample-echo",
        ),
        encoding="utf-8",
    )
    summary = publish_plugin(namespaced, public=False, org=TEST_ORG)
    assert summary["ok"] is True
    assert summary["package_kind"] == "plugin"
    assert summary["media_type"] == PLUGIN_MEDIA_TYPE
    assert "executor" in summary["slots_summary"]["provide"]
    ref = summary["ref"]

    client = RegistryClient(registry_server["url"], token=registry_server["token"])
    meta = client.get_metadata(database_id=summary["package_id"], version=summary["version"])
    assert meta.media_type == PLUGIN_MEDIA_TYPE
    # Raw client returns ReleaseInfo; full preview via direct HTTP
    import json
    import urllib.request

    path = f"/v1/packages/{summary['package_id']}/versions/{summary['version']}"
    req = urllib.request.Request(
        registry_server["url"] + path,
        headers={"Authorization": f"Bearer {registry_server['token']}"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
    assert body.get("package_kind") == "plugin"
    assert body.get("plugin_preview", {}).get("slots", {}).get("provide") == ["executor"]
    declared = body.get("plugin_preview", {}).get("declared") or []
    ids = {d.get("id") for d in declared}
    assert "executor" in ids
    assert "before_agent_invoke" in ids
    exec_row = next(d for d in declared if d.get("id") == "executor")
    assert exec_row.get("kind") == "provide"
    assert exec_row.get("level") == 2
    assert "plugin.yaml" in body.get("plugin_preview", {}).get("files", [])

    # Spec 06: list exposes package_kind without opening blob; filter works.
    list_req = urllib.request.Request(
        registry_server["url"] + "/v1/packages?package_kind=plugin",
        headers={"Authorization": f"Bearer {registry_server['token']}"},
    )
    with urllib.request.urlopen(list_req) as resp:  # noqa: S310
        listed = json.loads(resp.read().decode("utf-8"))
    plugin_items = listed.get("items") or []
    assert any(i.get("database_id") == summary["package_id"] for i in plugin_items)
    assert all(i.get("package_kind") == "plugin" for i in plugin_items)
    db_req = urllib.request.Request(
        registry_server["url"] + "/v1/packages?package_kind=database",
        headers={"Authorization": f"Bearer {registry_server['token']}"},
    )
    with urllib.request.urlopen(db_req) as resp:  # noqa: S310
        db_listed = json.loads(resp.read().decode("utf-8"))
    assert not any(
        i.get("database_id") == summary["package_id"] for i in (db_listed.get("items") or [])
    )

    installed = install_plugin_from_registry(ref)
    assert installed["ok"] is True
    assert installed["plugin_id"] == f"{TEST_ORG}/sample-echo"
    assert installed["digest"].startswith("sha256:")
    assert (home / "plugins" / "index.json").is_file()


def test_reject_database_as_plugin(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bora.registry.archive import build_archive
    from bora.registry.client import RegistryClient, RegistryError
    from bora.registry.digest import compute_package_digest

    monkeypatch.setenv("BORA_REGISTRY_URL", registry_server["url"])
    monkeypatch.setenv("BORA_REGISTRY_TOKEN", registry_server["token"])
    _ensure_org(registry_server["url"], registry_server["token"])

    db = REPO / "tests" / "fixtures" / "databases" / "publish-min"
    archive, blob_digest, size = build_archive(db)
    package_digest = compute_package_digest(db)
    client = RegistryClient(registry_server["url"], token=registry_server["token"])
    with pytest.raises(RegistryError) as ei:
        client.publish(
            database_id=f"{TEST_ORG}/not-a-plugin",
            version="0.0.1",
            package_digest=package_digest,
            blob_digest=blob_digest,
            size=size,
            media_type=PLUGIN_MEDIA_TYPE,
            visibility="private",
            archive=archive,
            org_id=TEST_ORG,
            package_kind="plugin",
        )
    # Server rejects with non-2xx (client maps to RegistryError).
    assert ei.value.status is None or ei.value.status >= 400
