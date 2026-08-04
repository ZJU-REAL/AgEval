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
from bora.adapters.child_env import cli_credential_available, project_cli_child_env


def _child_env(
    *,
    api_key_env: str | None = None,
    base_url: str | None = None,
) -> dict[str, str]:
    """Project only allowlisted credential locators into the child process."""
    return project_cli_child_env(
        "pi", api_key_env=api_key_env, base_url=base_url
    )


def credential_available(*, api_key_env: str | None = None) -> bool:
    return cli_credential_available("pi", api_key_env=api_key_env)



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
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.binary = binary or shutil.which("pi") or "pi"
        self.base_url = base_url
        self.api_key_env = api_key_env
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
        if not credential_available(api_key_env=self.api_key_env):
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
        child_env = _child_env(api_key_env=self.api_key_env, base_url=self.base_url)
        # pi resolves model→provider (e.g. glm → opencode) and may only accept the
        # key via --api-key for that path; also project aliases into child env.
        # Prefer env; pass CLI flag only when profile locator is set and present.
        if self.api_key_env and child_env.get(self.api_key_env):
            cmd.extend(["--api-key", child_env[self.api_key_env]])
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
                env=child_env,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            events, structured, text, usage, _backend_err = _parse_pi_jsonl(stdout)
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

        events, structured, text, usage, backend_err = _parse_pi_jsonl(proc.stdout or "")
        if structured is None and text:
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
        # pi often exits 0 even when the model call 401s; trust stopReason/errorMessage.
        ok = (
            proc.returncode == 0
            and backend_err is None
            and bool(text or structured)
        )
        if backend_err is not None:
            err: str | None = backend_err
        elif proc.returncode != 0:
            err = f"exit_{proc.returncode}"
        elif not (text or structured):
            err = "empty_response"
        else:
            err = None
        return AgentResult(
            model=self.model,
            text=(text or "")[-8000:],
            structured=structured if ok else None,
            ok=ok,
            error=err,
            stderr=(proc.stderr or "")[-8000:],
            events=events,
            source_refs=refs,
            usage=usage,
        )


def _message_text_parts(msg: dict[str, Any]) -> list[str]:
    content = msg.get("content")
    parts: list[str] = []
    if isinstance(content, str) and content.strip():
        parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                t = part["text"]
                if t.strip():
                    parts.append(t)
    return parts


def _parse_pi_jsonl(
    stdout: str,
) -> tuple[
    tuple[dict[str, Any], ...],
    dict[str, object] | None,
    str,
    dict[str, Any] | None,
    str | None,
]:
    """Parse pi ``--mode json`` JSONL.

    Only **assistant** message text counts as model output. User prompt text must
    not be treated as a successful response (avoids PASS on ``Return ONLY JSON
    {...}`` when the model 401s). Backend auth/stream errors set ``backend_err``.
    """
    events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    structured: dict[str, object] | None = None
    usage: dict[str, Any] | None = None
    backend_err: str | None = None

    def _note_error(msg: dict[str, Any]) -> None:
        nonlocal backend_err
        stop = msg.get("stopReason")
        err_msg = msg.get("errorMessage")
        if stop == "error" or (isinstance(err_msg, str) and err_msg.strip()):
            detail = err_msg if isinstance(err_msg, str) and err_msg.strip() else "backend_error"
            backend_err = detail[:500]

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

        msg = obj.get("message")
        if isinstance(msg, dict):
            role = str(msg.get("role") or "")
            _note_error(msg)
            # Only assistant (or missing role on pure assistant blobs) contributes output.
            if role == "assistant" or (role == "" and etype in {"message_end", "turn_end"}):
                text_parts.extend(_message_text_parts(msg))
            if isinstance(msg.get("usage"), dict):
                usage = msg["usage"]

        # Top-level text events (rare) — only if not a user message envelope.
        if etype == "text" and isinstance(obj.get("text"), str):
            text_parts.append(obj["text"])

        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]

        # agent_end may embed messages[] with the final assistant turn.
        if etype == "agent_end":
            embedded = obj.get("messages")
            if isinstance(embedded, list):
                for em in embedded:
                    if isinstance(em, dict) and em.get("role") == "assistant":
                        _note_error(em)
                        text_parts.extend(_message_text_parts(em))

    text = "\n".join(text_parts).strip()
    if structured is None and text and backend_err is None:
        structured = _try_parse_json_object(text)
    return tuple(events), structured, text, usage, backend_err
