"""Neutral trajectory fold: Core writer + ACP mapper (no ACP-shaped events)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora.adapters.acp.trajectory_map import acp_session_events_to_bora
from bora.evidence.schema import EVENT_SCHEMA_VERSION
from bora.evidence.trajectory import write_trajectory_jsonl


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _write(
    tmp: Path,
    events: Any,
    *,
    prompt: str = "p",
    final_text: str = "",
    structured: dict[str, object] | None = None,
    usage: dict[str, Any] | None = None,
    ok: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
    redaction_sentinels: list[str] | None = None,
) -> Path:
    return write_trajectory_jsonl(
        tmp / "inv",
        prompt=prompt,
        events=events,
        final_text=final_text,
        structured=structured,
        usage=usage,
        ok=ok,
        error=error,
        metadata=metadata,
        redaction_sentinels=redaction_sentinels,
    )


def test_writer_ignores_non_contract_events(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        events=(
            {"type": "session_update", "sessionUpdate": "tool_call", "toolCallId": "x"},
            {
                "schema": EVENT_SCHEMA_VERSION,
                "seq": 1,
                "source": "acp",
                "kind": "text",
                "channel": "assistant",
                "text": "hi",
            },
        ),
        prompt="hello",
        final_text="hi",
        usage={"input_tokens": 1},
        metadata={"executor_kind": "acp", "turn_index": 1},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert types == ["turn", "turn", "terminal"]
    assert "tool_call" not in types
    assert "acp_session_id" not in lines[0]
    assert lines[1]["source"] == "acp"
    assert lines[0]["source"] == "bora"


def test_no_tool_events_unchanged_shape(tmp_path: Path) -> None:
    mapped = acp_session_events_to_bora(
        (
            {
                "type": "session_update",
                "session_id": "s1",
                "channel": "assistant",
                "text": "hi ",
            },
            {
                "type": "session_update",
                "session_id": "s1",
                "channel": "assistant",
                "text": "there",
            },
        )
    )
    path = _write(
        tmp_path,
        events=mapped,
        prompt="hello",
        final_text="hi there",
        usage={"input_tokens": 1},
        metadata={"executor_kind": "acp", "turn_index": 1},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert types == ["turn", "turn", "terminal"]
    assert lines[0]["role"] == "user"
    assert lines[1]["role"] == "assistant"
    assert lines[1]["content"] == "hi there"
    assert lines[1]["session_id"] == "s1"
    assert "tool_call" not in types


def test_tool_call_and_update_merged(tmp_path: Path) -> None:
    events = (
        {
            "type": "session_update",
            "session_id": "sess_1",
            "update_type": "ToolCall",
            "tool_call_id": "call_001",
            "title": "Reading configuration file",
            "kind": "read",
            "status": "pending",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_001",
                "title": "Reading configuration file",
                "kind": "read",
                "status": "pending",
                "rawInput": {"path": "/workspace/config.json"},
            },
        },
        {
            "type": "session_update",
            "session_id": "sess_1",
            "update_type": "ToolCallUpdate",
            "tool_call_id": "call_001",
            "status": "in_progress",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_001",
                "status": "in_progress",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": "Found 3 configuration files..."},
                    }
                ],
            },
        },
        {
            "type": "session_update",
            "session_id": "sess_1",
            "update_type": "ToolCallUpdate",
            "tool_call_id": "call_001",
            "status": "completed",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_001",
                "status": "completed",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": "Analysis complete. Found 3 issues."},
                    }
                ],
                "rawOutput": {"ok": True, "count": 3},
            },
        },
        {
            "type": "session_update",
            "session_id": "sess_1",
            "channel": "assistant",
            "text": "Done.",
        },
    )
    path = _write(
        tmp_path,
        events=acp_session_events_to_bora(events),
        prompt="inspect config",
        final_text="Done.",
        metadata={"executor_kind": "acp", "acp_entry_id": "pi", "turn_index": 2},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert types == ["turn", "tool_call", "observation", "turn", "terminal"]

    tool = lines[1]
    assert tool["tool_call_id"] == "call_001"
    assert tool["kind"] == "read"
    assert tool["status"] == "completed"
    assert tool["args"] == {"path": "/workspace/config.json"}
    assert tool["title"] == "Reading configuration file"
    assert tool["function_name"] == "read"
    assert tool["turn_index"] == 2
    assert tool["session_id"] == "sess_1"
    assert tool["source"] == "acp"
    assert "acp_session_id" not in tool

    obs = lines[2]
    assert obs["type"] == "observation"
    assert obs["tool_call_id"] == "call_001"
    assert obs["status"] == "completed"
    assert "Analysis complete" in (obs.get("content") or "")
    assert obs["raw_output"] == {"ok": True, "count": 3}


def test_multiple_tool_calls_order_preserved(tmp_path: Path) -> None:
    events = (
        {
            "type": "session_update",
            "session_id": "s",
            "tool_call_id": "a",
            "title": "list",
            "kind": "search",
            "status": "completed",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "a",
                "title": "list",
                "kind": "search",
                "status": "completed",
                "rawInput": {"q": "x"},
                "content": [{"type": "content", "content": {"type": "text", "text": "a-out"}}],
            },
        },
        {
            "type": "session_update",
            "session_id": "s",
            "tool_call_id": "b",
            "title": "run",
            "kind": "execute",
            "status": "completed",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "b",
                "title": "run",
                "kind": "execute",
                "status": "completed",
                "rawInput": {"cmd": "ls"},
                "rawOutput": {"stdout": "ok"},
            },
        },
    )
    path = _write(tmp_path, events=acp_session_events_to_bora(events), prompt="p")
    lines = _read_lines(path)
    tool_ids = [x["tool_call_id"] for x in lines if x["type"] == "tool_call"]
    assert tool_ids == ["a", "b"]


def test_tool_args_redacted(tmp_path: Path) -> None:
    sentinel = "TRAJ_TOOL_SECRET_9f3a"
    events = (
        {
            "type": "session_update",
            "session_id": "s",
            "tool_call_id": "c1",
            "title": "fetch",
            "kind": "fetch",
            "status": "completed",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "c1",
                "title": "fetch",
                "kind": "fetch",
                "status": "completed",
                "rawInput": {"Authorization": f"Bearer {sentinel}", "token": sentinel},
                "rawOutput": {"body": f"cookie={sentinel}"},
            },
        },
    )
    path = _write(
        tmp_path,
        events=acp_session_events_to_bora(events),
        prompt=f"use {sentinel}",
        final_text="ok",
        redaction_sentinels=[sentinel],
    )
    blob = path.read_text(encoding="utf-8")
    assert sentinel not in blob
    assert "REDACTED" in blob


def test_terminal_meta_stdout_and_title_command(tmp_path: Path) -> None:
    """Pi/ACP path: command in title stream; stdout in update._meta.terminal_output."""
    events = (
        {
            "type": "session_update",
            "session_id": "s",
            "update_type": "ToolCallStart",
            "tool_call_id": "call_term",
            "title": "bash",
            "kind": "execute",
            "status": "pending",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_term",
                "title": "bash",
                "kind": "execute",
                "status": "pending",
                "content": [{"type": "terminal", "terminalId": "call_term"}],
            },
        },
        {
            "type": "session_update",
            "session_id": "s",
            "update_type": "ToolCallProgress",
            "tool_call_id": "call_term",
            "title": "ls -la /attempt/workspace/",
            "kind": "execute",
            "status": "pending",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_term",
                "title": "ls -la /attempt/workspace/",
                "kind": "execute",
                "status": "pending",
            },
        },
        {
            "type": "session_update",
            "session_id": "s",
            "update_type": "ToolCallProgress",
            "tool_call_id": "call_term",
            "status": "in_progress",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_term",
                "status": "in_progress",
                "_meta": {
                    "terminal_output": {
                        "data": "total 20\ndrwxr-xr-x 6 actor instruction.md\n",
                        "terminal_id": "call_term",
                    }
                },
            },
        },
        {
            "type": "session_update",
            "session_id": "s",
            "update_type": "ToolCallProgress",
            "tool_call_id": "call_term",
            "status": "completed",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_term",
                "status": "completed",
                "_meta": {"terminal_exit": {"exit_code": 0}},
            },
        },
    )
    path = _write(
        tmp_path,
        events=acp_session_events_to_bora(events),
        prompt="list dir",
        final_text="done",
    )
    lines = _read_lines(path)
    tool = next(x for x in lines if x["type"] == "tool_call")
    obs = next(x for x in lines if x["type"] == "observation")
    assert tool["args"] == {"command": "ls -la /attempt/workspace/"}
    assert tool["title"] == "ls -la /attempt/workspace/"
    assert tool["function_name"] == "execute"
    assert "total 20" in (obs.get("content") or "")
    assert "instruction.md" in (obs.get("content") or "")
    assert "[terminal" not in (obs.get("content") or "")


def test_permission_decision_still_emitted(tmp_path: Path) -> None:
    events = (
        {
            "type": "permission_decision",
            "outcome": "selected",
            "option_id": "allow-once",
            "policy": "batch_auto_approve",
            "source": "acp_client",
        },
    )
    path = _write(tmp_path, events=acp_session_events_to_bora(events), prompt="p")
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert "permission_decision" in types
    pe = next(x for x in lines if x["type"] == "permission_decision")
    assert pe["option_id"] == "allow-once"
    assert pe["source"] == "acp"


def test_opaque_not_folded(tmp_path: Path) -> None:
    events = (
        {
            "schema": EVENT_SCHEMA_VERSION,
            "seq": 1,
            "source": "nooa",
            "kind": "opaque",
            "payload": {"event_type": "BeforeTurn"},
        },
        {
            "schema": EVENT_SCHEMA_VERSION,
            "seq": 2,
            "source": "nooa",
            "kind": "text",
            "channel": "assistant",
            "text": "ok",
        },
    )
    path = _write(tmp_path, events=events, prompt="p", final_text="ok")
    lines = _read_lines(path)
    assert [x["type"] for x in lines] == ["turn", "turn", "terminal"]
    assert lines[1]["source"] == "nooa"
