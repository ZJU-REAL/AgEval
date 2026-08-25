"""openai-http: native tools= round-trip on a loopback mock; missing key fail-closed."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from ageval.plugins.contrib.openai_http.executor import OpenAIHTTPExecutor
from ageval.plugins.executor_capabilities import get_capabilities


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/v1"


def test_capability_matrix_is_native_tools() -> None:
    caps = get_capabilities("openai-http")
    assert caps is not None
    assert caps.tools == "native"
    assert caps.session == "new-only"
    assert caps.execution_mode == "api-client"


def test_missing_credential_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = OpenAIHTTPExecutor(base_url="https://api.example.invalid/v1").invoke("hi")
    assert result.ok is False
    assert result.error == "missing_credential"
    assert result.tool_calls == ()


def test_tools_round_trip_on_loopback() -> None:
    captured: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            captured["path"] = self.path
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "find_customer",
                                        "arguments": '{"email":"alex@example.com"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            del format, args

    server, base = _serve(Handler)
    try:
        result = OpenAIHTTPExecutor(model="mock", base_url=base).invoke(
            "lookup the customer",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "find_customer",
                        "parameters": {
                            "type": "object",
                            "properties": {"email": {"type": "string"}},
                        },
                    },
                }
            ],
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.ok is True
    assert result.tool_calls == (
        {
            "id": "call_1",
            "name": "find_customer",
            "arguments": {"email": "alex@example.com"},
        },
    )
    assert result.events == (
        {
            "kind": "tool",
            "phase": "start",
            "tool_call_id": "call_1",
            "function_name": "find_customer",
            "title": "find_customer",
            "args": {"email": "alex@example.com"},
            "status": "pending",
            "source": "openai-http",
        },
    )
    assert captured["path"].endswith("/chat/completions")
    assert "tools" in captured["body"]
    assert captured["body"]["tools"][0]["function"]["name"] == "find_customer"
    dumped = json.dumps(captured["body"])
    assert "sk-" not in dumped
    assert "Bearer" not in dumped
    assert "reasoning_effort" not in captured["body"]


def test_reasoning_effort_is_posted_when_set() -> None:
    captured: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            payload = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            del format, args

    server, base = _serve(Handler)
    try:
        result = OpenAIHTTPExecutor(
            model="mock",
            base_url=base,
            reasoning_effort="high",
        ).invoke("hi")
    finally:
        server.shutdown()
        server.server_close()

    assert result.ok is True
    assert captured["body"]["reasoning_effort"] == "high"
    assert result.metadata is not None
    assert result.metadata["locked_reasoning_effort"] == "high"
    assert result.metadata["actual_reasoning_effort"] == "high"


def test_reasoning_content_becomes_thought_event(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "need lookup first",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"q":"hi"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            del format, args

    server, base = _serve(Handler)
    collect = tmp_path / "raw"
    try:
        result = OpenAIHTTPExecutor(model="mock", base_url=base).invoke(
            "lookup",
            tools=[{"type": "function", "function": {"name": "lookup"}}],
            collect_dir=str(collect),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.text == ""
    assert result.events[0]["channel"] == "thought"
    assert result.events[0]["text"] == "need lookup first"
    assert result.events[1]["kind"] == "tool"
    dumped = json.loads((collect / "response.json").read_text(encoding="utf-8"))
    assert dumped["choices"][0]["message"]["reasoning_content"] == "need lookup first"


def test_omit_tools_keeps_content_path() -> None:
    captured: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            raw = json.dumps(
                {"choices": [{"message": {"role": "assistant", "content": '{"ok":true}'}}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            del format, args

    server, base = _serve(Handler)
    try:
        result = OpenAIHTTPExecutor(model="mock", base_url=base).invoke("hello")
    finally:
        server.shutdown()
        server.server_close()

    assert result.ok is True
    assert result.tool_calls == ()
    assert result.structured == {"ok": True}
    assert "tools" not in captured["body"]
