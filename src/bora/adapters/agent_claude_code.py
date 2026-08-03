"""Optional claude-code residual Adapter (v0.14a).

Only registered when ``claude`` / ``claude-code`` is on PATH. Not required for
the codex+pi+opencode Version Index gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from bora.adapters.agent_codex import (
    AgentResult,
    _maybe_persist_raw,
    _try_parse_json_object,
)


def _life(phase: str, *, source: str, **extra: object) -> dict[str, object]:
    ev: dict[str, object] = {"type": "lifecycle", "phase": phase, "source": source}
    ev.update(extra)
    return ev

class ClaudeCodeExecutor:
    kind: str = "claude-code"

    def __init__(self, *, model: str = "claude-haiku-4-5", binary: str | None = None) -> None:
        self.model = model
        self.binary = binary or shutil.which("claude") or shutil.which("claude-code") or "claude"

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 120.0,
        workdir: str | None = None,
        collect_dir: str | Path | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                events=(_life("skipped", source="claude_code_adapter"),),
            )
        if shutil.which(self.binary) is None:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="claude_code_binary_missing",
                events=(_life("failed", source="claude_code_adapter"),),
            )
        # Best-effort non-interactive print; flags may vary by CLI version.
        cmd = [self.binary, "-p", "--output-format", "json", prompt]
        collect_root = Path(collect_dir) if collect_dir else None
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
                cwd=workdir,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
                events=(_life("failed", source="claude_code_adapter"),),
            )
        text = proc.stdout or ""
        structured = _try_parse_json_object(text)
        refs = _maybe_persist_raw(
            collect_root,
            proc.stdout or "",
            proc.stderr or "",
            extra_sentinels=redaction_sentinels,
        )
        return AgentResult(
            model=self.model,
            text=text[-8000:],
            structured=structured,
            ok=proc.returncode == 0,
            error=None if proc.returncode == 0 else f"exit_{proc.returncode}",
            stderr=(proc.stderr or "")[-8000:],
            events=(
                _life("terminal", source="claude_code_adapter", returncode=proc.returncode),
            ),
            source_refs=refs,
        )
