#!/usr/bin/env python3
"""Minimal ACP-like NDJSON agent for offline protocol tests.

Not a full ACP server — only enough for unit framing experiments.
Production client tests use real entry binaries or offline_forced.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "result": {
                            "protocolVersion": 1,
                            "agentInfo": {"name": "echo-fixture", "version": "0"},
                            "agentCapabilities": {},
                        },
                    }
                ),
                flush=True,
            )
        elif method == "session/new":
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "result": {"sessionId": "sess-fixture"},
                    }
                ),
                flush=True,
            )
        elif method == "session/prompt":
            # session/update then result
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": "sess-fixture",
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": '{"answer": 42}'},
                            },
                        },
                    }
                ),
                flush=True,
            )
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "result": {"stopReason": "end_turn"},
                    }
                ),
                flush=True,
            )
        elif method in {"session/cancel", "session/close"}:
            if mid is not None:
                print(
                    json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}}),
                    flush=True,
                )
        else:
            if mid is not None:
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": mid,
                            "error": {"code": -32601, "message": "method not found"},
                        }
                    ),
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
