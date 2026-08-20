"""e2b download copies directory contents; files.read is files only."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ageval.environments.protocol import BoxSpec, EnvironmentFailure
from ageval.plugins.contrib.e2b.host import E2BHost


class FakeFiles:
    def __init__(self, files: dict[str, bytes], dirs: set[str]) -> None:
        self.files = files
        self.dirs = dirs
        self.reads: list[str] = []

    def get_info(self, path: str) -> SimpleNamespace:
        if path in self.files:
            return SimpleNamespace(path=path, type="file")
        if path in self.dirs:
            return SimpleNamespace(path=path, type="dir")
        raise FileNotFoundError(path)

    def list(self, path: str, depth: int = 1) -> list[SimpleNamespace]:
        del depth
        prefix = path.rstrip("/") + "/"
        entries: list[SimpleNamespace] = []
        seen_dirs: set[str] = set()
        for file_path in self.files:
            if not file_path.startswith(prefix):
                continue
            rest = file_path[len(prefix) :]
            first, _, more = rest.partition("/")
            if more:
                child = f"{path.rstrip('/')}/{first}"
                if child not in seen_dirs:
                    seen_dirs.add(child)
                    entries.append(SimpleNamespace(path=child, type="dir"))
            else:
                entries.append(SimpleNamespace(path=file_path, type="file"))
        return entries

    def read(self, path: str, format: str = "text") -> bytes | str:
        self.reads.append(path)
        payload = self.files[path]
        return bytearray(payload) if format == "bytes" else payload.decode()


class FakeSandbox:
    def __init__(self, files: FakeFiles) -> None:
        self.files = files


def _host(tmp_path: Path, files: FakeFiles) -> E2BHost:
    host = E2BHost(spec=BoxSpec(attempt_root=tmp_path, task_root=tmp_path, repo_root=tmp_path))
    host._started = True
    host._sandbox = FakeSandbox(files)
    return host


@pytest.mark.asyncio
async def test_download_directory_copies_contents_not_a_nested_folder(tmp_path: Path) -> None:
    files = FakeFiles(
        {
            "/attempt/workspace/aggregates.json": b'{"ok": true}',
            "/attempt/workspace/nested/out.txt": b"hello",
        },
        {"/attempt/workspace", "/attempt/workspace/nested"},
    )
    dest = tmp_path / "task-workspace"
    dest.mkdir()
    await _host(tmp_path, files).download("/attempt/workspace", dest)

    assert (dest / "aggregates.json").read_bytes() == b'{"ok": true}'
    assert (dest / "nested" / "out.txt").read_text(encoding="utf-8") == "hello"
    assert not (dest / "workspace").exists()
    assert "/attempt/workspace" not in files.reads


@pytest.mark.asyncio
async def test_download_file_writes_dest(tmp_path: Path) -> None:
    files = FakeFiles({"/attempt/workspace/aggregates.json": b"{}"}, set())
    dest = tmp_path / "out" / "aggregates.json"
    await _host(tmp_path, files).download("/attempt/workspace/aggregates.json", dest)
    assert dest.read_bytes() == b"{}"


@pytest.mark.asyncio
async def test_download_missing_path_is_environment_failure(tmp_path: Path) -> None:
    host = _host(tmp_path, FakeFiles({}, set()))
    with pytest.raises(EnvironmentFailure, match="does not exist"):
        await host.download("/attempt/workspace/missing", tmp_path / "x")
