"""Spec 08: public second-backend (openai-http) via production bora run + local mock."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        _ = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"answer": 42}),
                        }
                    }
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def test_plugin_agent_executor_http_public_pass() -> None:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env["BORA_OPENAI_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
        env["OPENAI_API_KEY"] = "test-local-mock"
        env.pop("BORA_OFFLINE_AGENT", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "bora.cli.main",
                "run",
                str(REPO / "examples" / "core"),
                "--task",
                "plugin-agent-executor",
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(REPO),
            env=env,
            timeout=120,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        data = json.loads(result.stdout)
        assert data["status"] == "PASS"
        assert data["score"] == 1.0
    finally:
        server.shutdown()
