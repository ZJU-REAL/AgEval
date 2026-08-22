"""Second AgentExecutor: OpenAI-compatible HTTP Chat backend.

Thin executor only — no Run/credential store ownership beyond scoped API key env.
Profile may supply ``base_url`` and ``api_key`` (env locator name).
Native ``tools=`` is first-class; omit the catalog to keep the content path.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ageval.plugins.agent_result import AgentExecutor, AgentResult

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_KEY_ENV = "OPENAI_API_KEY"


def _chat_messages(
    prompt: str, messages: Sequence[Mapping[str, Any]] | None
) -> list[dict[str, Any]]:
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
        out = [dict(item) for item in messages if isinstance(item, Mapping)]
        if out:
            return out
    return [{"role": "user", "content": prompt}]


def _normalize_tools(tools: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        return []
    out: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "function" and isinstance(item.get("function"), Mapping):
            out.append(dict(item))
            continue
        name = str(item.get("name") or "")
        if not name:
            fn = item.get("function")
            if isinstance(fn, Mapping):
                name = str(fn.get("name") or "")
                if name:
                    out.append({"type": "function", "function": dict(fn)})
            continue
        spec: dict[str, Any] = {"name": name}
        if item.get("description"):
            spec["description"] = item["description"]
        if isinstance(item.get("parameters"), Mapping):
            spec["parameters"] = dict(item["parameters"])
        out.append({"type": "function", "function": spec})
    return out


def _parse_tool_calls(raw: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        fn = item.get("function") if isinstance(item.get("function"), Mapping) else item
        if not isinstance(fn, Mapping):
            continue
        name = str(fn.get("name") or item.get("name") or "")
        if not name:
            continue
        args: Any = fn.get("arguments") if "arguments" in fn else item.get("arguments")
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except json.JSONDecodeError:
                parsed = {}
            args = parsed if isinstance(parsed, dict) else {}
        elif not isinstance(args, dict):
            args = {}
        out.append(
            {
                "id": str(item.get("id") or ""),
                "name": name,
                "arguments": args,
            }
        )
    return tuple(out)


@dataclass
class OpenAIHTTPExecutor(AgentExecutor):
    """Minimal HTTP executor; credentials from host env via locator name."""

    kind: str = "openai-http"
    model: str = "gpt-4.1-mini"
    base_url: str | None = None
    api_key_env: str | None = None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        messages: Sequence[Mapping[str, Any]] | None = None,
    ) -> AgentResult:
        del collect_dir, redaction_sentinels
        key_env = self.api_key_env or _DEFAULT_KEY_ENV
        key = os.environ.get(key_env, "")
        base = self.base_url or os.environ.get("AGEVAL_OPENAI_BASE_URL") or _DEFAULT_BASE
        # Allow explicit empty-key local mock servers only when base_url is loopback.
        if not key and "127.0.0.1" not in base and "localhost" not in base:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="missing_credential",
            )
        from ageval.runtime.offline import is_offline_agent

        if is_offline_agent() and "127.0.0.1" not in base and "localhost" not in base:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
            )
        url = f"{base.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _chat_messages(prompt, messages),
            "temperature": 0,
        }
        catalog = _normalize_tools(tools)
        if catalog:
            payload["tools"] = catalog
        body = json.dumps(payload).encode("utf-8")
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
        message: Mapping[str, Any] = {}
        try:
            choice0 = raw["choices"][0]
            found = choice0["message"]
            if isinstance(found, Mapping):
                message = found
        except (KeyError, IndexError, TypeError):
            message = {}
        text = message.get("content") if isinstance(message.get("content"), str) else ""
        if not text and not message:
            text = json.dumps(raw)[:4000]
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        structured = None
        try:
            structured = json.loads(text) if text else None
            if not isinstance(structured, dict):
                structured = None
        except json.JSONDecodeError:
            structured = None
        events = tuple(
            {
                "type": "tool_call",
                "id": call["id"],
                "name": call["name"],
                "source": "openai-http",
            }
            for call in tool_calls
        )
        return AgentResult(
            model=self.model,
            text=(text or "")[-8000:],
            structured=structured,
            ok=True,
            error=None,
            events=events,
            tool_calls=tool_calls,
        )
