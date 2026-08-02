"""Built-in Codex AgentExecutor (v0.6).

Runs non-interactive ``codex exec`` with an explicit model. Credentials stay in
the executor child environment only (host login / CODEX_* as provided by OS).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentResult:
    model: str
    text: str
    structured: dict[str, object] | None
    ok: bool
    error: str | None = None


class CodexExecutor:
    """Minimal first-party Codex executor."""

    def __init__(self, *, model: str = "gpt-5.4-mini", binary: str | None = None) -> None:
        self.model = model
        self.binary = binary or shutil.which("codex") or "codex"

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 45.0,
        workdir: str | None = None,
    ) -> AgentResult:
        # Tests/CI can force offline to avoid long-running network calls.
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
            )
        if shutil.which(self.binary) is None and self.binary == "codex":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="codex_binary_missing",
            )
        # Prefer non-interactive exec; flags best-effort across CLI versions.
        cmd = [
            self.binary,
            "exec",
            "--model",
            self.model,
            "--ephemeral",
            prompt,
        ]
        cwd = workdir if workdir else None
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
                cwd=cwd,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"{type(exc).__name__}",
            )
        text = (proc.stdout or "") + (proc.stderr or "")
        structured = _try_parse_json_object(proc.stdout or "")
        return AgentResult(
            model=self.model,
            text=text[-8000:],
            structured=structured,
            ok=proc.returncode == 0,
            error=None if proc.returncode == 0 else f"exit_{proc.returncode}",
        )


def _try_parse_json_object(text: str) -> dict[str, object] | None:
    text = text.strip()
    if not text:
        return None
    # Try full stdout as JSON, else last {...} block.
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.rfind("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None
    return None
