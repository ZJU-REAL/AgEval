"""ACP trajectory synthesis: tool_call + observation from session/update events."""

from __future__ import annotations

import json
from pathlib import Path

from bora.adapters.acp.trajectory import write_trajectory_jsonl


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_no_tool_events_unchanged_shape(tmp_path: Path) -> None:
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="hello",
        events=(
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
        ),
        final_text="hi there",
        structured=None,
        usage={"input_tokens": 1},
        ok=True,
        error=None,
        metadata={"executor_kind": "acp", "turn_index": 1},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert types == ["turn", "turn", "terminal"]
    assert lines[0]["role"] == "user"
    assert lines[1]["role"] == "assistant"
    assert lines[1]["content"] == "hi there"
    assert "tool_call" not in types
    assert "observation" not in types


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
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="inspect config",
        events=events,
        final_text="Done.",
        structured=None,
        usage=None,
        ok=True,
        error=None,
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
    assert tool["function_name"] == "read"  # Harbor: kind when present
    assert tool["turn_index"] == 2
    assert tool["acp_session_id"] == "sess_1"

    obs = lines[2]
    assert obs["type"] == "observation"
    assert obs["tool_call_id"] == "call_001"
    assert obs["status"] == "completed"
    # Harbor joins observation chunks (in_progress + completed text)
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
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="p",
        events=events,
        final_text="",
        structured=None,
        usage=None,
        ok=True,
        error=None,
    )
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
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt=f"use {sentinel}",
        events=events,
        final_text="ok",
        structured=None,
        usage=None,
        ok=True,
        error=None,
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
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="list dir",
        events=events,
        final_text="done",
        structured=None,
        usage=None,
        ok=True,
        error=None,
    )
    lines = _read_lines(path)
    tool = next(x for x in lines if x["type"] == "tool_call")
    obs = next(x for x in lines if x["type"] == "observation")
    assert tool["args"] == {"command": "ls -la /attempt/workspace/"}
    assert tool["title"] == "ls -la /attempt/workspace/"
    assert tool["function_name"] == "execute"  # Harbor: kind over title token
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
    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="p",
        events=events,
        final_text="",
        structured=None,
        usage=None,
        ok=True,
        error=None,
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert "permission_decision" in types
