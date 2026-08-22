"""terminal-jsonl-agg publishes from disk, never from truncated chat."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "examples" / "journeys" / "tasks" / "terminal-jsonl-agg"
if str(TASK) not in sys.path:
    sys.path.insert(0, str(TASK))

from run import run  # noqa: E402


class _Session:
    def __init__(self, reply: dict[str, object]) -> None:
        self.reply = reply

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def invoke(self, instruction: str) -> dict[str, object]:
        del instruction
        return self.reply


class _Ctx:
    def __init__(self, tmp: Path, *, reply: dict[str, object], on_disk: dict | None) -> None:
        self.workspace_root = tmp / "ws"
        self.workspace_root.mkdir()
        (self.workspace_root / "instruction.md").write_text("agg\n", encoding="utf-8")
        if on_disk is not None:
            (self.workspace_root / "aggregates.json").write_text(
                json.dumps(on_disk), encoding="utf-8"
            )
        self.artifact_dir = tmp / "arts"
        self.artifact_dir.mkdir()
        self.params = SimpleNamespace(
            get=lambda key, default=None: {
                "workspace_output": "aggregates.json",
                "active_profile": "solver",
                "models": {"default": "solver"},
            }.get(key, default)
        )
        self.agent = SimpleNamespace(session=lambda *a, **k: _Session(reply))
        self.published: dict[str, object] = {}

    def publish_json(self, artifact_id: str, data: object) -> Path:
        path = self.artifact_dir / f"{artifact_id}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.published[artifact_id] = data
        return path


_TRUNCATED = (
    "`aggregates.json` written:\n\n```json\n{\n"
    '  "top_5_users_by_amount": {\n'
    '    "carol": {"total_amount": 70.0, "total_items": 5},\n   '
)


@pytest.mark.asyncio
async def test_truncated_chat_does_not_publish(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path, reply={"ok": True, "text": _TRUNCATED}, on_disk=None)
    terminal = await run(ctx)  # type: ignore[arg-type]
    assert terminal.kind.value == "completed"
    assert ctx.published == {}


@pytest.mark.asyncio
async def test_shared_disk_file_is_published(tmp_path: Path) -> None:
    payload = {"top_5_users_by_amount": {"alice": {"total_amount": 1.0, "total_items": 1}}}
    ctx = _Ctx(tmp_path, reply={"ok": True, "text": _TRUNCATED}, on_disk=payload)
    terminal = await run(ctx)  # type: ignore[arg-type]
    assert terminal.kind.value == "completed"
    assert ctx.published["aggregates"] == payload
