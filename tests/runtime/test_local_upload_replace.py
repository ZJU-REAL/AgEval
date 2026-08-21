"""Directory upload replaces the dest tree instead of merging leftover files."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.helpers.box import local_box

from ageval.environments.protocol import EVALUATION_PATH


@pytest.mark.asyncio
async def test_local_directory_upload_replaces_dest(tmp_path: Path) -> None:
    host = local_box(tmp_path / "attempt")
    await host.start()
    dest = host.host_path(EVALUATION_PATH)
    dest.mkdir(parents=True)
    (dest / "planted.txt").write_text("agent", encoding="utf-8")
    (dest / "gold.json").write_text('{"stale": true}\n', encoding="utf-8")

    source = tmp_path / "gold"
    source.mkdir()
    (source / "gold.json").write_text('{"ok": true}\n', encoding="utf-8")

    await host.upload(source, EVALUATION_PATH)

    assert (dest / "gold.json").read_text(encoding="utf-8") == '{"ok": true}\n'
    assert not (dest / "planted.txt").exists()
    await host.stop(delete=True)
