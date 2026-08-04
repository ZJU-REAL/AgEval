"""Second AgentExecutor: OpenAI-compatible HTTP Responses/Chat backend (v0.9).

Thin executor only — no Run/credential store ownership beyond scoped API key env.
Profile may supply ``base_url`` and ``api_key`` (env locator name).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from bora.adapters.agent_codex import AgentResult

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_KEY_ENV = "OPENAI_API_KEY"


@dataclass
class OpenAIHTTPExecutor:
    """Minimal HTTP executor; credentials from host env via locator name."""

    model: str = "gpt-4.1-mini"
    base_url: str | None = None
    api_key_env: str | None = None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del workdir, collect_dir, redaction_sentinels  # unused on HTTP path
        key_env = self.api_key_env or _DEFAULT_KEY_ENV
        key = os.environ.get(key_env, "")
        base = (
            self.base_url
            or os.environ.get("BORA_OPENAI_BASE_URL")
            or _DEFAULT_BASE
        )
        # Allow explicit empty-key local mock servers only when base_url is loopback.
        if not key and "127.0.0.1" not in base and "localhost" not in base:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="missing_credential",
            )
        if os.environ.get("BORA_OFFLINE_AGENT") == "1" and "127.0.0.1" not in base:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
            )
        url = f"{base.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
            )
        text = ""
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            text = json.dumps(raw)[:4000]
        structured = None
        try:
            structured = json.loads(text)
            if not isinstance(structured, dict):
                structured = None
        except json.JSONDecodeError:
            structured = None
        return AgentResult(
            model=self.model,
            text=text[-8000:],
            structured=structured,
            ok=True,
            error=None,
        )


def resolve_executor(
    kind: str,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> Any:
    """Registry: map locked executor kind → implementation (entry-point aware)."""
    from bora.adapters.agent_registry import resolve_executor as _resolve

    return _resolve(kind, model=model, base_url=base_url, api_key=api_key)
