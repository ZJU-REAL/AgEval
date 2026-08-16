"""In-flight upload cap: 429 when slots are exhausted."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from services.registry.app import build_default_state, make_handler
from services.registry.errors import RegistryAppError
from services.registry.upload_slots import UploadSlotPool

from bora.registry.client import RegistryClient, RegistryError


def test_pool_hold_and_exhaust() -> None:
    pool = UploadSlotPool(1)
    with pool.hold():
        with pytest.raises(RegistryAppError) as ei, pool.hold():
            raise AssertionError("must not enter")
        assert ei.value.error == "too_many_uploads"
        assert ei.value.http_status == 429
    with pool.hold():
        pass


def test_http_429_when_slot_held(tmp_path: Path) -> None:
    state, token = build_default_state(
        tmp_path / "data", bootstrap_token="slot-token", memory_blob=True
    )
    state.upload_slots = UploadSlotPool(1)
    handler = make_handler(state)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        client = RegistryClient(url, token=token)
        assert client.health()["ok"] is True
        with state.upload_slots.hold():
            bogus = tmp_path / "nope.bin"
            bogus.write_bytes(b"nope")
            with pytest.raises(RegistryError) as ei:
                client.publish(
                    database_id="test/publish-min",
                    version="0.1.0",
                    package_digest="sha256:" + "ab" * 32,
                    blob_digest="sha256:" + "cd" * 32,
                    size=4,
                    media_type="application/vnd.bora.database.v1.tar+gzip",
                    visibility="private",
                    archive=bogus,
                    org_id="test",
                )
            assert ei.value.status == 429
            assert ei.value.code == "too_many_uploads"
    finally:
        server.shutdown()
