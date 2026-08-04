"""Built-in opencode AgentExecutor (v0.14).

Non-interactive: ``opencode run --format json``. Credentials only in child env
via allowlisted locators (values never logged).
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
    _as_text,
    _maybe_persist_raw,
    _try_parse_json_object,
)
from bora.adapters.child_env import cli_credential_available, project_cli_child_env


def _child_env(
    *,
    api_key_env: str | None = None,
    base_url: str | None = None,
) -> dict[str, str]:
    return project_cli_child_env(
        "opencode", api_key_env=api_key_env, base_url=base_url
    )


def credential_available(*, api_key_env: str | None = None) -> bool:
    # Host may store opencode auth under XDG (values never read into evidence).
    auth = Path.home() / ".local/share/opencode/auth.json"
    return cli_credential_available(
        "opencode",
        api_key_env=api_key_env,
        extra_ok=auth.is_file(),
    )



def _life(phase: str, *, source: str, **extra: object) -> dict[str, object]:
    ev: dict[str, object] = {"type": "lifecycle", "phase": phase, "source": source}
    ev.update(extra)
    return ev


def _is_error_event(e: dict[str, object]) -> bool:
    if e.get("type") == "error":
        return True
    payload = e.get("payload")
    return isinstance(payload, dict) and payload.get("type") == "error"

class OpenCodeExecutor:
    """First-party opencode CLI executor."""

    kind: str = "opencode"

    def __init__(
        self,
        *,
        model: str = "zai-coding-plan/glm-4.7",
        binary: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self.model = model
        self.binary = binary or shutil.which("opencode") or "opencode"
        self.base_url = base_url
        self.api_key_env = api_key_env

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 180.0,
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
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "skipped",
                        "reason": "offline_forced",
                        "source": "opencode_adapter",
                    },
                ),
            )
        if shutil.which(self.binary) is None and self.binary == "opencode":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="opencode_binary_missing",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "opencode_binary_missing",
                        "source": "opencode_adapter",
                    },
                ),
            )
        # Prefer env locators; allow host auth.json residual via full HOME for opencode only
        # when no env key — still never copy secrets into evidence.
        auth_json = Path.home() / ".local/share/opencode/auth.json"
        if not credential_available(api_key_env=self.api_key_env) and not auth_json.is_file():
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="missing_credential",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "missing_credential",
                        "source": "opencode_adapter",
                    },
                ),
            )

        cmd = [
            self.binary,
            "run",
            "--format",
            "json",
            "--model",
            self.model,
            "--pure",
            prompt,
        ]
        collect_root = Path(collect_dir) if collect_dir else None
        if collect_root is not None:
            collect_root.mkdir(parents=True, exist_ok=True)

        # Opencode may need HOME for auth.json; still restrict env keys we inject.
        env = _child_env(api_key_env=self.api_key_env, base_url=self.base_url)
        if not credential_available(api_key_env=self.api_key_env):
            # Fall back to host HOME only (auth.json path); do not dump entire os.environ.
            env["HOME"] = os.environ.get("HOME", "")
            env["PATH"] = os.environ.get("PATH", "")

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            events, structured, text, usage = _parse_opencode_jsonl(stdout)
            events = events + (
                {"type": "lifecycle", "phase": "timeout", "source": "opencode_adapter"},
            )
            refs = _maybe_persist_raw(
                collect_root, stdout, stderr, extra_sentinels=redaction_sentinels
            )
            return AgentResult(
                model=self.model,
                text=text[-8000:],
                structured=structured,
                ok=False,
                error="TimeoutExpired",
                stderr=stderr[-8000:],
                events=events,
                source_refs=refs,
                usage=usage,
            )
        except OSError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "crash",
                        "reason": type(exc).__name__,
                        "source": "opencode_adapter",
                    },
                ),
            )

        events, structured, text, usage = _parse_opencode_jsonl(proc.stdout or "")
        # Detect JSON error events as failure even when exit 0.
        has_error_event = any(
            _is_error_event(e)
            for e in events
        )
        if structured is None:
            structured = _try_parse_json_object(text)
        events = events + (
            {
                "type": "lifecycle",
                "phase": "terminal",
                "returncode": proc.returncode,
                "source": "opencode_adapter",
            },
        )
        refs = _maybe_persist_raw(
            collect_root,
            proc.stdout or "",
            proc.stderr or "",
            extra_sentinels=redaction_sentinels,
        )
        ok = proc.returncode == 0 and not has_error_event and bool(text or structured)
        return AgentResult(
            model=self.model,
            text=(text or "")[-8000:],
            structured=structured,
            ok=ok,
            error=None if ok else (f"exit_{proc.returncode}" if proc.returncode else "backend_err"),
            stderr=(proc.stderr or "")[-8000:],
            events=events,
            source_refs=refs,
            usage=usage,
        )


def _parse_opencode_jsonl(
    stdout: str,
) -> tuple[tuple[dict[str, Any], ...], dict[str, object] | None, str, dict[str, Any] | None]:
    events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    structured: dict[str, object] | None = None
    usage: dict[str, Any] | None = None
    for line in (stdout or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            events.append({"type": "backend_raw_line", "line": raw[:2000], "source": "opencode"})
            continue
        if not isinstance(obj, dict):
            continue
        etype = str(obj.get("type") or "backend")
        events.append({"type": etype, "payload": obj, "source": "opencode"})
        if etype == "error":
            continue
        # Message / text extraction from opencode event stream shapes.
        part = obj.get("part")
        if isinstance(part, dict):
            for key in ("text", "content", "output"):
                val = part.get(key)
                if isinstance(val, str) and val.strip():
                    text_parts.append(val)
        for key in ("text", "content", "message"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                text_parts.append(val)
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
    text = "\n".join(text_parts).strip()
    if structured is None and text:
        structured = _try_parse_json_object(text)
    return tuple(events), structured, text, usage
