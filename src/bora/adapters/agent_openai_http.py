"""Second AgentExecutor: OpenAI-compatible HTTP Responses/Chat backend (v0.9).

Thin executor only — no Run/credential store ownership beyond scoped API key env.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from bora.adapters.agent_codex import AgentResult


@dataclass
class OpenAIHTTPExecutor:
    """Minimal HTTP executor using OPENAI_API_KEY from environment."""

    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
    ) -> AgentResult:
        key = os.environ.get(self.api_key_env, "")
        # Allow explicit empty-key local mock servers only when base_url is overridden.
        if not key and "127.0.0.1" not in self.base_url and "localhost" not in self.base_url:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="missing_credential",
            )
        if os.environ.get("BORA_OFFLINE_AGENT") == "1" and "127.0.0.1" not in self.base_url:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
            )
        # Env override for second-backend / local mock (scoped to Executor process).
        base = os.environ.get("BORA_OPENAI_BASE_URL") or self.base_url
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


def resolve_executor(kind: str, *, model: str) -> Any:
    """Registry: map locked executor kind → implementation (entry-point aware)."""
    from bora.adapters.agent_registry import resolve_executor as _resolve

    return _resolve(kind, model=model)
