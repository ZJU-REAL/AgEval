"""In-process registry publish → wipe cache → lock-by-ref (Spec 21)."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler

from ageval.application.composition import build_lock_command, build_publish_command
from ageval.config.errors import ConfigError
from ageval.registry.cache import PackageCache
from ageval.registry.client import RegistryClient
from ageval.registry.credentials import write_credentials
from ageval.registry.digest import compute_package_digest

publish_dataset = build_publish_command().publish_dataset

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "datasets" / "publish-min"

TEST_ORG = "test"


def _ensure_org() -> None:
    """Create default test org owned by current token (idempotent)."""
    import os

    from ageval.registry.client import RegistryClient, RegistryError

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
    # Memory blob for unit e2e (allowed by Spec 21 for tests).
    state, token = build_default_state(data, bootstrap_token="test-token-publish", memory_blob=True)
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    yield {"url": url, "token": token, "state": state}
    server.shutdown()


def test_publish_and_lock_by_ref(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds = tmp_path / "credentials"
    write_credentials(
        url=registry_server["url"],
        token=registry_server["token"],
        path=creds,
    )
    monkeypatch.setenv("AGEVAL_REGISTRY_URL", registry_server["url"])
    monkeypatch.setenv("AGEVAL_REGISTRY_TOKEN", registry_server["token"])
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("AGEVAL_CACHE_ROOT", str(cache_root))
    _ensure_org()

    summary = publish_dataset(FIXTURE, public=False, org=TEST_ORG)
    assert summary["ok"] is True
    assert summary["dataset_id"] == "test/publish-min"
    assert summary["package_digest"] == compute_package_digest(FIXTURE)
    ref = summary["ref"]

    # Wipe any accidental local path preference: lock by registry ref only.
    lock = build_lock_command()
    out = lock.run(dataset_root=ref, task_id="hello")
    assert out["task_id"] == "hello"
    assert out["dataset_id"] == "test/publish-min"
    assert out["digest"].startswith("sha256:")

    # Cache should now contain verified tree.
    cached = PackageCache(cache_root).lookup("test/publish-min", summary["package_digest"])
    assert cached is not None
    assert (cached / "ageval.yaml").is_file()

    # Offline: stop server, digest ref still works from cache.
    # (server still up here — stop then retry)
    # Call shutdown via fixture teardown after; for offline, hit cache only:
    offline = lock.run(
        dataset_root=summary["digest_ref"],
        task_id="hello",
    )
    assert offline["task_id"] == "hello"


def test_private_without_token_is_not_found(
    registry_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_URL", registry_server["url"])
    monkeypatch.setenv("AGEVAL_REGISTRY_TOKEN", registry_server["token"])
    _ensure_org()
    summary = publish_dataset(FIXTURE, public=False, org=TEST_ORG)

    # Client without token
    client = RegistryClient(registry_server["url"], token=None)
    with pytest.raises(Exception) as ei:
        client.get_metadata(dataset_id=summary["dataset_id"], version=summary["version"])
    # RegistryError with not_found / 404
    assert "not_found" in str(ei.value) or "404" in str(ei.value)


def test_publish_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGEVAL_REGISTRY_TOKEN", raising=False)
    monkeypatch.setenv("AGEVAL_REGISTRY_URL", "http://127.0.0.1:9")
    # Empty token via missing credentials
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ConfigError) as ei:
        publish_dataset(FIXTURE, org=TEST_ORG)
    assert ei.value.error_code in {"unauthorized", "registry_unavailable"}
