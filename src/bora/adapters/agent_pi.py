"""Built-in pi AgentExecutor (v0.14).

Non-interactive: ``pi -p --mode json --no-session``. Credentials only in child env
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
from bora.adapters.executor_capabilities import BUILTIN_CAPABILITIES


def _child_env() -> dict[str, str]:
    """Project only allowlisted credential locators into the child process."""
    caps = BUILTIN_CAPABILITIES["pi"]
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
        "TERM": "dumb",
        "PI_OFFLINE": os.environ.get("PI_OFFLINE", ""),
    }
    # Map common host aliases → ZAI without logging values.
    if not os.environ.get("ZAI_API_KEY"):
        for alias in ("ZHIPU_API_KEY", "zhipu_coding_api_key", "ZHIPU_CODING_API_KEY"):
            if os.environ.get(alias):
                env["ZAI_API_KEY"] = os.environ[alias]
                break
    for name in caps.credential_env_names:
        val = os.environ.get(name)
        if val:
            env[name] = val
    # Drop empty keys.
    return {k: v for k, v in env.items() if v}


def credential_available() -> bool:
    env = _child_env()
    return any(env.get(name) for name in BUILTIN_CAPABILITIES["pi"].credential_env_names)



def _life(phase: str, *, source: str, **extra: object) -> dict[str, object]:
    ev: dict[str, object] = {"type": "lifecycle", "phase": phase, "source": source}
    ev.update(extra)
    return ev

class PiExecutor:
    """First-party pi CLI executor."""

    kind: str = "pi"

    def __init__(
        self,
        *,
        model: str = "claude-haiku-4-5",
        provider: str | None = None,
        binary: str | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.binary = binary or shutil.which("pi") or "pi"
        # Support model as "provider/model".
        if provider is None and "/" in model:
            self.provider, self.model = model.split("/", 1)

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
                events=(_life("skipped", source="pi_adapter", reason="offline_forced"),),
            )
        if shutil.which(self.binary) is None and self.binary == "pi":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="pi_binary_missing",
                events=(_life("failed", source="pi_adapter", reason="pi_binary_missing"),),
            )
        if not credential_available():
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="missing_credential",
                events=(_life("failed", source="pi_adapter", reason="missing_credential"),),
            )

        cmd = [
            self.binary,
            "-p",
            "--mode",
            "json",
            "--no-session",
            "--no-tools",
            "--model",
            self.model,
        ]
        if self.provider:
            cmd.extend(["--provider", self.provider])
        cmd.append(prompt)

        collect_root = Path(collect_dir) if collect_dir else None
        if collect_root is not None:
            collect_root.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_child_env(),
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            events, structured, text, usage = _parse_pi_jsonl(stdout)
            events = events + ({"type": "lifecycle", "phase": "timeout", "source": "pi_adapter"},)
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
                events=(_life("crash", source="pi_adapter", reason=type(exc).__name__),),
            )

        events, structured, text, usage = _parse_pi_jsonl(proc.stdout or "")
        if structured is None:
            structured = _try_parse_json_object(text)
        events = events + (
            {
                "type": "lifecycle",
                "phase": "terminal",
                "returncode": proc.returncode,
                "source": "pi_adapter",
            },
        )
        refs = _maybe_persist_raw(
            collect_root,
            proc.stdout or "",
            proc.stderr or "",
            extra_sentinels=redaction_sentinels,
        )
        return AgentResult(
            model=self.model,
            text=(text or "")[-8000:],
            structured=structured,
            ok=proc.returncode == 0 and bool(text or structured),
            error=None if proc.returncode == 0 else f"exit_{proc.returncode}",
            stderr=(proc.stderr or "")[-8000:],
            events=events,
            source_refs=refs,
            usage=usage,
        )


def _parse_pi_jsonl(
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
            events.append({"type": "backend_raw_line", "line": raw[:2000], "source": "pi"})
            continue
        if not isinstance(obj, dict):
            continue
        etype = str(obj.get("type") or "backend")
        events.append({"type": etype, "payload": obj, "source": "pi"})
        # Common pi message shapes.
        for key in ("message", "text", "content"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                text_parts.append(val)
        msg = obj.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
    text = "\n".join(text_parts).strip()
    if structured is None and text:
        structured = _try_parse_json_object(text)
    return tuple(events), structured, text, usage
