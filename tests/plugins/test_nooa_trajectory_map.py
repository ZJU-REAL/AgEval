"""nooa native dump → bora.trajectory.event/1 (no ACP masquerade)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bora.evidence.trajectory import write_trajectory_jsonl

_NOOA_SRC = Path(__file__).resolve().parents[2] / "plugins" / "nooa" / "src"
if str(_NOOA_SRC) not in sys.path:
    sys.path.insert(0, str(_NOOA_SRC))

from nooa_plugin.trajectory import SCHEMA, to_bora_trajectory_events  # noqa: E402


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_python_output_folds_to_tool_observation(tmp_path: Path) -> None:
    native = (
        {"event_type": "Task", "prompt": "sum the jsonl"},
        {
            "event_type": "PythonOutput",
            "tool_call_id": "py1",
            "execution_status": "complete",
            "stdout": "42\n",
            "stderr": "",
            "error": "",
            "value": 42,
        },
        {"event_type": "Message", "content": "answer is 42"},
        {"event_type": "BeforeTurn", "method_name": "run"},
    )
    mapped = to_bora_trajectory_events(native)
    assert all(e.get("schema") == SCHEMA for e in mapped)
    assert all(e.get("source") == "nooa" for e in mapped)
    assert not any("sessionUpdate" in e or e.get("type") == "session_update" for e in mapped)
    kinds = [e["kind"] for e in mapped]
    assert "BeforeTurn" not in {e.get("payload", {}).get("event_type") for e in mapped}
    assert kinds.count("tool") == 2

    path = write_trajectory_jsonl(
        tmp_path / "inv",
        prompt="sum the jsonl",
        events=mapped,
        final_text="answer is 42",
        structured=None,
        usage=None,
        ok=True,
        error=None,
        metadata={"executor_kind": "nooa", "plugin": "nooa"},
    )
    lines = _read_lines(path)
    types = [x["type"] for x in lines]
    assert "tool_call" in types
    assert "observation" in types
    tool = next(x for x in lines if x["type"] == "tool_call")
    obs = next(x for x in lines if x["type"] == "observation")
    assert tool["function_name"] == "execute_python"
    assert tool["source"] == "nooa"
    assert "acp_session_id" not in tool
    assert "42" in (obs.get("content") or "")


def test_tool_call_event_with_result() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "ToolCallEvent",
                "tool_call_id": "c1",
                "name": "read_file",
                "arguments": {"path": "/tmp/a"},
                "result": {"ok": True, "text": "hi"},
            },
        )
    )
    phases = [(e["kind"], e.get("phase")) for e in mapped]
    assert phases == [("tool", "start"), ("tool", "update")]
    assert mapped[1]["status"] == "completed"
    assert mapped[0]["args"] == {"path": "/tmp/a"}


def test_python_output_derives_elapsed_from_vendor_timestamp() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "ToolCallEvent",
                "id": "vendor-1",
                "tool_call_id": "c1",
                "name": "execute_python",
                "arguments": {"code": "print(1)"},
                "timestamp": "2026-08-14T12:00:00.000Z",
                "at": "2026-08-14T12:00:59Z",
            },
            {
                "event_type": "PythonOutput",
                "id": "vendor-1-out",
                "tool_call_id": "c1",
                "execution_status": "complete",
                "stdout": "1\n",
                "timestamp": "2026-08-14T12:00:01.250Z",
                "at": "2026-08-14T12:00:59Z",
            },
        )
    )
    start = next(e for e in mapped if e.get("phase") == "start")
    update = next(e for e in mapped if e.get("phase") == "update")
    assert start["at"] == "2026-08-14T12:00:00.000Z"
    assert update["elapsed_ms"] == 1250.0


def test_mapper_skips_tap_duplicates_when_vendor_tools_exist() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "ToolCallEvent",
                "id": "tap_py_4",
                "tool_call_id": "tap_py_4",
                "name": "execute_python",
                "at": "2026-08-14T12:00:00.000Z",
            },
            {
                "event_type": "PythonOutput",
                "id": "tap_py_4_out",
                "tool_call_id": "tap_py_4",
                "execution_status": "complete",
                "stdout": "x",
                "at": "2026-08-14T12:00:00.001Z",
            },
            {
                "event_type": "ToolCallEvent",
                "id": "vendor-1",
                "tool_call_id": "c1",
                "name": "execute_python",
                "timestamp": "2026-08-14T12:00:00.000Z",
            },
            {
                "event_type": "PythonOutput",
                "id": "vendor-1-out",
                "tool_call_id": "c1",
                "execution_status": "complete",
                "stdout": "x",
                "timestamp": "2026-08-14T12:00:00.400Z",
            },
        )
    )
    tools = [e for e in mapped if e.get("kind") == "tool"]
    ids = {e.get("tool_call_id") for e in tools}
    assert ids == {"c1"}
    update = next(e for e in tools if e.get("phase") == "update")
    assert update["elapsed_ms"] == 400.0


def test_llmcomplete_does_not_steal_execute_span() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "LLMComplete",
                "id": "tap_llmcomplete_3",
                "tool_calls": [
                    {
                        "tool_call_id": "c1",
                        "function_name": "execute_python",
                        "arguments": {"code": "print(1)"},
                    }
                ],
            },
            {
                "event_type": "ToolCallEvent",
                "id": "vendor-1",
                "tool_call_id": "c1",
                "name": "execute_python",
                "arguments": {"code": "print(1)"},
                "result": {"ok": True},
                "timestamp": "2026-08-14T12:00:00.000Z",
            },
            {
                "event_type": "PythonOutput",
                "id": "vendor-1-out",
                "tool_call_id": "c1",
                "execution_status": "complete",
                "stdout": "1\n",
                "timestamp": "2026-08-14T12:00:00.080Z",
            },
        )
    )
    starts = [e for e in mapped if e.get("kind") == "tool" and e.get("phase") == "start"]
    assert len(starts) == 1
    update = next(
        e
        for e in mapped
        if e.get("kind") == "tool" and e.get("phase") == "update" and e.get("elapsed_ms")
    )
    assert update["elapsed_ms"] == 80.0


def test_tool_call_copies_vendor_elapsed_ms() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "ToolCallEvent",
                "tool_call_id": "c1",
                "name": "read_file",
                "arguments": {"path": "/tmp/a"},
                "result": {"ok": True, "text": "hi"},
                "elapsed_ms": 88,
                "at": "2026-08-14T12:00:01Z",
            },
        )
    )
    update = next(e for e in mapped if e.get("phase") == "update")
    assert update["elapsed_ms"] == 88.0
    assert update["at"] == "2026-08-14T12:00:01Z"


def test_return_result_emits_assistant_with_last_llm_elapsed() -> None:
    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "LLMCallStart",
                "at": "2026-08-14T12:00:00.000Z",
            },
            {
                "event_type": "LLMCallEnd",
                "at": "2026-08-14T12:00:08.405Z",
            },
            {
                "event_type": "LLMComplete",
                "reasoning_content": "return the aggregates",
            },
            {
                "event_type": "ToolCallEvent",
                "tool_call_id": "ret1",
                "name": "return_result",
                "arguments": {"result": {"ok": True}},
                "timestamp": "2026-08-14T12:00:08.406Z",
            },
        )
    )
    thought = next(e for e in mapped if e.get("channel") == "thought")
    assert thought["elapsed_ms"] == 8405.0
    assistant = next(e for e in mapped if e.get("channel") == "assistant")
    assert assistant["elapsed_ms"] == 8405.0
    assert "ok" in assistant["text"]
    tools = [e for e in mapped if e.get("kind") == "tool"]
    assert any(e.get("function_name") == "return_result" for e in tools)


async def _passthrough(value: object) -> object:
    return value


def test_collect_does_not_stamp_foreign_contract_events() -> None:
    import asyncio

    from nooa_plugin.hooks import trajectory_collect

    payload = {
        "events": (
            {
                "schema": SCHEMA,
                "kind": "assistant",
                "source": "acp",
                "session_id": "s1",
                "text": "hi",
            },
        ),
        "metadata": {"executor_kind": "acp"},
    }
    out = asyncio.run(trajectory_collect(None, payload, _passthrough))
    assert isinstance(out, dict)
    assert out["metadata"].get("trajectory_source") != "nooa"
    assert out["events"][0]["source"] == "acp"


def test_collect_maps_native_and_stamps_nooa() -> None:
    import asyncio

    from nooa_plugin.hooks import trajectory_collect

    payload = {
        "events": (
            {
                "event_type": "ToolCallEvent",
                "tool_call_id": "c1",
                "name": "read_file",
                "arguments": {"path": "/tmp/a"},
            },
        ),
        "metadata": {},
    }
    out = asyncio.run(trajectory_collect(None, payload, _passthrough))
    assert isinstance(out, dict)
    assert out["metadata"]["trajectory_source"] == "nooa"
    assert out["events"]
    assert all(e.get("schema") == SCHEMA for e in out["events"])
    assert all(e.get("source") == "nooa" for e in out["events"])


class _FakeEventManager:
    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}

    def on(self, event_type: str, handler: object) -> object:
        self._handlers.setdefault(event_type, []).append(handler)

        def _unsub() -> None:
            self._handlers.get(event_type, []).remove(handler)

        return _unsub

    def intercept(self, kind: str, fn: object) -> object:
        del kind, fn

        def _unsub() -> None:
            return None

        return _unsub

    def emit(self, ev: object) -> None:
        for key in ("*", getattr(ev, "event_type", None)):
            if not key:
                continue
            for handler in list(self._handlers.get(key, [])):
                handler(ev)

    def items(self) -> list:
        return []


class _FakeAgent:
    def __init__(self, em: _FakeEventManager) -> None:
        self.event_manager = em


class _FakeEvent:
    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)
        self.event_type = str(fields.get("event_type") or type(self).__name__)

    def model_dump(self, mode: str = "python") -> dict:
        del mode
        return dict(self.__dict__)


def test_event_tap_keeps_notify_only_runtime_events() -> None:
    from nooa_plugin.trajectory import attach_event_tap, to_bora_trajectory_events

    em = _FakeEventManager()
    agent = _FakeAgent(em)
    tap = attach_event_tap(agent)
    em.emit(
        _FakeEvent(
            id="c1",
            event_type="LLMComplete",
            reasoning_content="plan the aggregation",
            tool_calls=[
                {
                    "tool_call_id": "call_1",
                    "function_name": "execute_python",
                    "arguments": {"code": "print(1)"},
                }
            ],
        )
    )
    em.emit(
        _FakeEvent(
            id="p1",
            event_type="PythonOutput",
            tool_call_id="call_1",
            execution_status="complete",
            stdout="1\n",
        )
    )
    native = tap.finish(agent)
    kinds = [r.get("event_type") for r in native]
    assert "LLMComplete" in kinds
    assert "PythonOutput" in kinds
    mapped = to_bora_trajectory_events(native)
    channels = [e.get("channel") for e in mapped if e.get("kind") == "text"]
    assert "thought" in channels
    tools = [e for e in mapped if e.get("kind") == "tool"]
    assert any(e.get("function_name") == "execute_python" for e in tools)
    assert any(e.get("phase") == "update" and "1" in str(e.get("content")) for e in tools)


def test_llm_complete_tool_calls_fold_without_duplicate() -> None:
    from nooa_plugin.trajectory import to_bora_trajectory_events

    mapped = to_bora_trajectory_events(
        (
            {
                "event_type": "LLMComplete",
                "tool_calls": [
                    {
                        "tool_call_id": "c1",
                        "function_name": "execute_python",
                        "arguments": {"code": "x=1"},
                    }
                ],
                "reasoning_content": "think",
            },
            {
                "event_type": "ToolCallEvent",
                "tool_call_id": "c1",
                "name": "execute_python",
                "arguments": {"code": "x=1"},
                "result": {"stdout": "ok"},
            },
        )
    )
    starts = [e for e in mapped if e.get("kind") == "tool" and e.get("phase") == "start"]
    assert len(starts) == 1
    thoughts = [e for e in mapped if e.get("channel") == "thought"]
    assert thoughts and "think" in thoughts[0]["text"]
