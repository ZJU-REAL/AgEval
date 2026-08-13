"""dsh native dump → bora.trajectory.event/1 (no ACP masquerade)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bora.evidence.trajectory import write_trajectory_jsonl

_DSH_SRC = Path(__file__).resolve().parents[2] / "plugins" / "dsh" / "src"
if str(_DSH_SRC) not in sys.path:
    sys.path.insert(0, str(_DSH_SRC))

from dsh_plugin.trajectory import (  # noqa: E402
    SCHEMA,
    extract_finish_reason,
    extract_usage,
    to_bora_trajectory_events,
)


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_tool_call_and_result_map_to_layer_b(tmp_path: Path) -> None:
    native = (
        {
            "type": "assistant/message",
            "data": {
                "message": {
                    "content": [
                        {"type": "reasoning", "text": "I will run bash."},
                        {
                            "type": "tool-call",
                            "id": "call_1",
                            "name": "bash",
                            "arguments": '{"command": "echo hi"}',
                        },
                    ]
                },
                "usage": {
                    "inputTokens": 10,
                    "outputTokens": 4,
                    "cacheReadTokens": 2,
                    "reasoningTokens": 3,
                },
            },
        },
        {
            "type": "tool/call",
            "data": {
                "callId": "call_1",
                "name": "bash",
                "arguments": '{"command": "echo hi"}',
            },
        },
        {
            "type": "tool/result",
            "data": {
                "message": {
                    "source": {"kind": "tool", "callId": "call_1"},
                    "content": [
                        {
                            "type": "tool-result",
                            "toolCallId": "call_1",
                            "content": [{"type": "text", "text": "hi\n"}],
                            "isError": False,
                        }
                    ],
                }
            },
        },
        {
            "type": "assistant/message",
            "data": {"message": {"content": [{"type": "text", "text": "hi"}]}},
        },
        {"type": "turn/end", "data": {"reason": {"kind": "completed"}}},
        {"type": "assistant/chunk", "data": {"chunk": {"type": "text", "text": "skip"}}},
    )
    mapped = to_bora_trajectory_events(native, session_id="bora-s")
    assert all(e.get("schema") == SCHEMA for e in mapped)
    assert all(e.get("source") == "dsh" for e in mapped)
    assert all(e.get("session_id") == "bora-s" for e in mapped)
    assert not any("sessionUpdate" in e or e.get("type") == "session_update" for e in mapped)
    kinds = [e["kind"] for e in mapped]
    assert kinds.count("tool") == 2
    thought = next(e for e in mapped if e.get("channel") == "thought")
    assert "bash" in thought["text"]
    assistant = next(e for e in mapped if e.get("channel") == "assistant")
    assert assistant["text"] == "hi"
    start = next(e for e in mapped if e.get("kind") == "tool" and e.get("phase") == "start")
    assert start["function_name"] == "bash"
    assert start["tool_call_id"] == "call_1"
    assert start["args"]["command"] == "echo hi"
    update = next(e for e in mapped if e.get("kind") == "tool" and e.get("phase") == "update")
    assert update["function_name"] == "bash"
    assert "hi" in (update.get("content") or "")
    assert extract_finish_reason(native) == "completed"
    usage = extract_usage(native)
    assert usage is not None
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 4
    assert usage["cache_read_tokens"] == 2
    assert usage["total_tokens"] == 14

    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="echo hi",
        events=mapped,
        final_text="hi",
        structured=None,
        usage=usage,
        ok=True,
        error=None,
        metadata={"executor_kind": "dsh", "plugin": "dsh"},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert "tool_call" in types
    assert "observation" in types
    tool = next(x for x in lines if x["type"] == "tool_call")
    assert tool["source"] == "dsh"
    assert "acp_session_id" not in tool


def test_extract_usage_sums_committed_steps_not_last_or_chunks() -> None:
    native = (
        {
            "type": "assistant/chunk",
            "data": {
                "chunk": {
                    "type": "usage",
                    "usage": {
                        "inputTokens": 1914,
                        "outputTokens": 81,
                        "cacheReadTokens": 0,
                        "reasoningTokens": 15,
                    },
                }
            },
        },
        {
            "type": "assistant/message",
            "data": {
                "usage": {
                    "inputTokens": 1914,
                    "outputTokens": 81,
                    "cacheReadTokens": 0,
                    "reasoningTokens": 15,
                }
            },
        },
        {
            "type": "assistant/message",
            "data": {
                "usage": {
                    "inputTokens": 238,
                    "outputTokens": 196,
                    "cacheReadTokens": 4096,
                    "reasoningTokens": 0,
                }
            },
        },
    )
    assert extract_usage(native) == {
        "input_tokens": 2152,
        "output_tokens": 277,
        "cache_read_tokens": 4096,
        "reasoning_tokens": 15,
        "total_tokens": 2429,
    }


def test_foreign_wrapped_event_unwraps() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "method": "session.event",
                "sessionId": "s",
                "event": {
                    "type": "tool/call",
                    "data": {"callId": "c2", "name": "read_file", "arguments": {"path": "a"}},
                },
            },
        )
    )
    assert mapped[0]["function_name"] == "read_file"
    assert mapped[0]["args"]["path"] == "a"


def test_tool_result_copies_vendor_elapsed_ms() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "type": "tool/call",
                "timestamp": "2026-08-14T12:00:00Z",
                "data": {"callId": "c1", "name": "bash", "arguments": {"command": "echo"}},
            },
            {
                "type": "tool/result",
                "timestamp": "2026-08-14T12:00:01Z",
                "data": {
                    "elapsed_ms": 1000,
                    "message": {
                        "source": {"kind": "tool", "callId": "c1"},
                        "content": [
                            {
                                "type": "tool-result",
                                "toolCallId": "c1",
                                "content": [{"type": "text", "text": "ok"}],
                            }
                        ],
                    },
                },
            },
        )
    )
    start = next(e for e in mapped if e.get("phase") == "start")
    update = next(e for e in mapped if e.get("phase") == "update")
    assert start["at"] == "2026-08-14T12:00:00Z"
    assert update["elapsed_ms"] == 1000.0
    assert update["at"] == "2026-08-14T12:00:01Z"
