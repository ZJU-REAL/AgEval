"""After writers stop, missing publishable files come from the box workspace."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ageval.attempt.artifact_harvest import harvest_workspace_artifacts
from ageval.environments.protocol import (
    ARTIFACTS_PATH,
    WORKSPACE_PATH,
    EnvironmentCapabilities,
    EnvironmentFailure,
)


class _Evidence:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        return self.root / name


class _Host:
    def __init__(self, files: dict[str, bytes], *, download: bool = True) -> None:
        self.files = files
        self.capabilities = EnvironmentCapabilities(download=download)
        self.downloads: list[tuple[str, Path]] = []

    async def download(self, source: str, dest: Path) -> None:
        self.downloads.append((source, dest))
        if source not in self.files:
            raise EnvironmentFailure("environment_download_missing", source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.files[source])


def _ctx(tmp_path: Path, host: _Host, *, stopped: bool = True) -> SimpleNamespace:
    facts: list[dict[str, object]] = []

    def record_fact(name: str, detail: dict[str, object] | None = None) -> None:
        facts.append({"name": name, "detail": dict(detail or {})})

    def assert_writers_stopped() -> None:
        if not stopped:
            raise RuntimeError("agent writers not confirmed stopped before evaluate")

    return SimpleNamespace(
        host=host,
        lock=SimpleNamespace(
            resolved_references={
                "artifacts": [{"id": "aggregates", "path": "artifacts/aggregates.json"}]
            }
        ),
        evidence=_Evidence(tmp_path),
        record_fact=record_fact,
        assert_writers_stopped=assert_writers_stopped,
        facts=facts,
    )


@pytest.mark.asyncio
async def test_harvest_pulls_workspace_basename_first(tmp_path: Path) -> None:
    payload = b'{"top_5_users_by_amount": {"alice": {"total_amount": 1, "total_items": 1}}}\n'
    host = _Host(
        {
            f"{WORKSPACE_PATH}/aggregates.json": payload,
            f"{WORKSPACE_PATH}/artifacts/aggregates.json": b'{"stale":true}\n',
        }
    )
    ctx = _ctx(tmp_path, host)
    await harvest_workspace_artifacts(ctx)
    dest = tmp_path / "task-artifacts" / "aggregates.json"
    assert dest.read_bytes() == payload
    assert host.downloads[0][0] == f"{WORKSPACE_PATH}/aggregates.json"
    assert ctx.facts[-1]["detail"]["pulled"] == ["aggregates"]


@pytest.mark.asyncio
async def test_harvest_pulls_missing_workspace_file(tmp_path: Path) -> None:
    payload = b'{"top_5_users_by_amount": {}}\n'
    source = f"{WORKSPACE_PATH}/artifacts/aggregates.json"
    host = _Host({source: payload})
    ctx = _ctx(tmp_path, host)
    await harvest_workspace_artifacts(ctx)
    dest = tmp_path / "task-artifacts" / "aggregates.json"
    assert dest.read_bytes() == payload
    assert host.downloads[-1] == (source, dest)
    assert ctx.facts[-1]["detail"]["pulled"] == ["aggregates"]


@pytest.mark.asyncio
async def test_harvest_falls_back_to_artifacts_dir(tmp_path: Path) -> None:
    payload = b'{"from":"artifacts"}\n'
    host = _Host({f"{ARTIFACTS_PATH}/aggregates.json": payload})
    ctx = _ctx(tmp_path, host)
    await harvest_workspace_artifacts(ctx)
    dest = tmp_path / "task-artifacts" / "aggregates.json"
    assert dest.read_bytes() == payload
    assert host.downloads[-1][0] == f"{ARTIFACTS_PATH}/aggregates.json"


@pytest.mark.asyncio
async def test_harvest_skips_when_run_py_already_published(tmp_path: Path) -> None:
    dest = tmp_path / "task-artifacts" / "aggregates.json"
    dest.parent.mkdir(parents=True)
    dest.write_text('{"from":"run.py"}\n', encoding="utf-8")
    host = _Host({f"{WORKSPACE_PATH}/aggregates.json": b'{"from":"box"}\n'})
    ctx = _ctx(tmp_path, host)
    await harvest_workspace_artifacts(ctx)
    assert dest.read_text(encoding="utf-8") == '{"from":"run.py"}\n'
    assert host.downloads == []
    assert ctx.facts[-1]["detail"]["skipped"] == ["aggregates"]


@pytest.mark.asyncio
async def test_harvest_missing_box_file_does_not_raise(tmp_path: Path) -> None:
    host = _Host({})
    ctx = _ctx(tmp_path, host)
    await harvest_workspace_artifacts(ctx)
    assert not (tmp_path / "task-artifacts" / "aggregates.json").exists()
    assert ctx.facts[-1]["detail"]["missing"] == ["aggregates"]


@pytest.mark.asyncio
async def test_harvest_requires_writers_stopped(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, _Host({}), stopped=False)
    with pytest.raises(RuntimeError, match="writers"):
        await harvest_workspace_artifacts(ctx)
