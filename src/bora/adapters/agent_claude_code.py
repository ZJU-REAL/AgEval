"""Optional claude-code residual Adapter (v0.14a).

Only registered when ``claude`` / ``claude-code`` is on PATH. Not required for
the codex+pi+opencode Version Index gate.

Supports profile ``base_url`` + ``api_key`` (env locator) for Anthropic-compatible
gateways (e.g. GLM Coding Plan via open.bigmodel.cn/api/anthropic).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bora.adapters.agent_codex import (
    AgentResult,
    _maybe_persist_raw,
    _try_parse_json_object,
)
from bora.adapters.child_env import project_cli_child_env


def _life(phase: str, *, source: str, **extra: object) -> dict[str, object]:
    ev: dict[str, object] = {"type": "lifecycle", "phase": phase, "source": source}
    ev.update(extra)
    return ev


def _extract_text_and_structured(stdout: str) -> tuple[str, dict[str, object] | None]:
    """Parse Claude Code ``--output-format json`` envelope or raw text."""
    raw = (stdout or "").strip()
    if not raw:
        return "", None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        structured = _try_parse_json_object(raw)
        return raw[-8000:], structured
    if not isinstance(obj, dict):
        return raw[-8000:], None
    # Prefer the agent result string inside the CLI envelope.
    result = obj.get("result")
    if isinstance(result, str) and result.strip():
        structured = _try_parse_json_object(result)
        if structured is None and result.strip().startswith("{"):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    structured = parsed
            except json.JSONDecodeError:
                pass
        return result[-8000:], structured
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)[-8000:], result
    structured = _try_parse_json_object(raw)
    return raw[-8000:], structured


class ClaudeCodeExecutor:
    kind: str = "claude-code"

    def __init__(
        self,
        *,
        model: str = "claude-haiku-4-5",
        binary: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self.model = model
        self.binary = binary or shutil.which("claude") or shutil.which("claude-code") or "claude"
        self.base_url = base_url
        self.api_key_env = api_key_env

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
        # Non-interactive print; model is first-class from the locked profile.
        cmd = [
            self.binary,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            prompt,
        ]
        collect_root = Path(collect_dir) if collect_dir else None
        # Allowlisted projection (same helper as pi/opencode) — not full host env.
        child_env = project_cli_child_env(
            "claude-code",
            api_key_env=self.api_key_env,
            base_url=self.base_url,
        )
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=child_env,
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
        text, structured = _extract_text_and_structured(proc.stdout or "")
        # Envelope may set is_error even when exit 0.
        envelope_err = False
        try:
            env_obj = json.loads((proc.stdout or "").strip())
            if isinstance(env_obj, dict) and env_obj.get("is_error") is True:
                envelope_err = True
        except json.JSONDecodeError:
            pass
        refs = _maybe_persist_raw(
            collect_root,
            proc.stdout or "",
            proc.stderr or "",
            extra_sentinels=redaction_sentinels,
        )
        ok = proc.returncode == 0 and not envelope_err and bool(text or structured)
        events: tuple[dict[str, Any], ...] = (
            _life(
                "terminal",
                source="claude_code_adapter",
                returncode=proc.returncode,
                model=self.model,
            ),
        )
        return AgentResult(
            model=self.model,
            text=text,
            structured=structured,
            ok=ok,
            error=None if ok else (f"exit_{proc.returncode}" if proc.returncode else "backend_err"),
            stderr=(proc.stderr or "")[-8000:],
            events=events,
            source_refs=refs,
        )
