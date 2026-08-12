"""nooa ExecutorSPI — host path for NVIDIA OO Agents (real LLM via LiteLLM).

Mirrors NVIDIA ``nooa-bench`` runner wiring:

    llm = get_llm_client(model, api_base=..., api_key=...)
    agent = AgentClass(llm=llm)
    result = await agent.<method>(prompt, workdir=...)

``api_key`` on the profile is an env *locator name* (never a secret value).
``base_url`` is the OpenAI-compatible endpoint (profile or env fallback).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import os
from typing import Any

from bora.adapters.agent_contract import AgentResult
from bora.plugins.errors import ExtensionMaterializeError

PLUGIN_ID = "nooa"

# Env fallbacks when profile omits base_url (non-secret locators / common names).
_BASE_URL_ENV_FALLBACKS = (
    "OPENAI_BASE_URL",
    "litellm_base_url",
    "BORA_OPENAI_BASE_URL",
)


def _resolve_api_key_value(locator: str | None) -> str | None:
    if not locator or not str(locator).strip():
        return None
    name = str(locator).strip()
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()
    # Common alias when profile uses openai-style locator.
    if name != "OPENAI_API_KEY":
        alt = os.environ.get("OPENAI_API_KEY")
        if alt and alt.strip():
            return alt.strip()
    return None


def _resolve_base_url(explicit: str | None) -> str | None:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    for key in _BASE_URL_ENV_FALLBACKS:
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def _run_coro(coro: Any) -> Any:
    """Run *coro* from sync ExecutorSPI.invoke (may already be inside a loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _is_nooa_agent_type(obj: Any) -> bool:
    try:
        from nooa import Agent as NooaAgent
    except ImportError:
        return False
    return isinstance(obj, type) and issubclass(obj, NooaAgent)


def _normalize_raw(raw: Any, *, model: str, agent_ref: str, collect_dir: str | None) -> AgentResult:
    if isinstance(raw, AgentResult):
        return raw
    # Pydantic v2
    if hasattr(raw, "model_dump") and callable(raw.model_dump):
        try:
            dumped = raw.model_dump()
            if isinstance(dumped, dict):
                raw = dumped
        except Exception:  # noqa: BLE001
            pass
    if isinstance(raw, dict):
        structured = raw.get("structured")
        if not isinstance(structured, dict):
            # Whole dict is the payload when agent returns domain JSON directly.
            if "ok" in raw or "text" in raw or "error" in raw:
                structured = (
                    raw["structured"] if isinstance(raw.get("structured"), dict) else None
                )
                if structured is None:
                    structured = {
                        k: v for k, v in raw.items() if k not in {"ok", "error", "text"}
                    } or None
            else:
                structured = raw
        text = str(raw.get("text") or "")
        if not text and structured is not None:
            import json

            try:
                text = json.dumps(structured, ensure_ascii=False)
            except TypeError:
                text = str(structured)
        return AgentResult(
            model=model,
            text=text,
            structured=structured if isinstance(structured, dict) else None,
            ok=bool(raw.get("ok", True)),
            error=str(raw["error"]) if raw.get("error") else None,
            metadata={
                "plugin": PLUGIN_ID,
                "agent": agent_ref,
                "collect_dir": str(collect_dir or ""),
                "llm_backed": True,
            },
        )
    text = str(raw) if raw is not None else ""
    structured = None
    try:
        import json

        parsed = json.loads(text)
        if isinstance(parsed, dict):
            structured = parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return AgentResult(
        model=model,
        text=text,
        structured=structured,
        ok=True,
        metadata={
            "plugin": PLUGIN_ID,
            "agent": agent_ref,
            "llm_backed": True,
        },
    )


class NooaExecutorSPI:
    """ExecutorSPI: load package agent + invoke via NVIDIA nooa + real LLM.

    Host SPI for L0. L1 Ready uses in-container worker (``bora-executor-nooa``).
    Plain (non-``nooa.Agent``) classes remain supported for deterministic probes
    such as slot-probe ``FixedAnswerAgent`` / unit fixtures — those paths do not
    call the network.
    """

    kind = "nooa"

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        profile_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        plugin_id: str | None = None,
        **_kwargs: Any,
    ) -> None:
        del plugin_id
        opts = dict(options or {})
        agent_ref = opts.get("agent")
        if not agent_ref or not str(agent_ref).strip():
            raise ExtensionMaterializeError(
                "nooa_options_agent_required",
                kind="extension_materialize_failed",
            )
        self.agent_ref = str(agent_ref).strip()
        self.method = str(opts.get("method") or "run").strip() or "run"
        self.profile_id = profile_id
        self.model = (model or "").strip() or "openai/gpt-4.1-mini"
        self.base_url = base_url
        self.api_key_env = api_key  # locator name
        self.options = opts
        self.default_workdir = str(opts.get("_workdir")).strip() if opts.get("_workdir") else None
        self._agent_cls: Any = None
        self._agent: Any = None
        self._llm: Any = None
        self._llm_backed = False
        self._ready = False

    def open(self, **kwargs: Any) -> None:
        del kwargs
        self._agent_cls = self._load_agent_class()
        self._llm_backed = _is_nooa_agent_type(self._agent_cls)
        if self._llm_backed:
            self._llm = self._build_llm()
            self._agent = self._agent_cls(llm=self._llm)
        else:
            cls = self._agent_cls
            self._agent = cls() if callable(cls) else cls
        self._ready = True

    def close(self) -> None:
        self._agent = None
        self._agent_cls = None
        self._llm = None
        self._ready = False

    def _build_llm(self) -> Any:
        try:
            from nooa.unifiedllm import get_llm_client
        except ImportError as exc:
            raise ExtensionMaterializeError(
                "nooa_package_missing: install the NVIDIA nooa package "
                "(uv sync --extra nooa / pip install nooa)",
                kind="extension_materialize_failed",
            ) from exc

        from bora.runtime.offline import is_offline_agent

        base = _resolve_base_url(self.base_url if isinstance(self.base_url, str) else None)
        key = _resolve_api_key_value(
            self.api_key_env if isinstance(self.api_key_env, str) else None
        )
        if is_offline_agent():
            raise ExtensionMaterializeError(
                "offline_forced",
                kind="extension_materialize_failed",
            )
        if not key and not (base and ("127.0.0.1" in base or "localhost" in base)):
            raise ExtensionMaterializeError(
                f"nooa_missing_credential: env {self.api_key_env!r} unset "
                f"(and no loopback base_url)",
                kind="extension_materialize_failed",
            )
        overrides: dict[str, Any] = {"temperature": 0}
        if base:
            overrides["api_base"] = base
        if key:
            overrides["api_key"] = key
        return get_llm_client(self.model, **overrides)

    def _load_agent_class(self) -> Any:
        import sys
        from pathlib import Path

        ref = self.agent_ref
        if ":" in ref:
            mod_name, cls_name = ref.split(":", 1)
        else:
            mod_name, cls_name = ref, None
        roots: list[Path] = []
        for key in ("_package_root", "package_root"):
            raw = self.options.get(key)
            if isinstance(raw, str) and raw.strip():
                roots.append(Path(raw).expanduser().resolve(strict=False))
        roots.append(Path.cwd())
        for root in roots:
            s = str(root)
            if root.is_dir() and s not in sys.path:
                sys.path.insert(0, s)
        try:
            import importlib

            mod = importlib.import_module(mod_name)
        except Exception as exc:  # noqa: BLE001
            raise ExtensionMaterializeError(
                f"nooa_agent_import_failed:{exc}",
                kind="extension_materialize_failed",
            ) from exc
        if cls_name:
            cls = getattr(mod, cls_name, None)
            if cls is None:
                raise ExtensionMaterializeError(
                    f"nooa_agent_class_missing:{cls_name}",
                    kind="extension_materialize_failed",
                )
            return cls
        return mod

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del timeout, redaction_sentinels
        effective_workdir = workdir or self.default_workdir
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        if not self._ready or self._agent is None:
            try:
                self.open()
            except ExtensionMaterializeError as exc:
                return AgentResult(
                    model=self.model,
                    text="",
                    structured=None,
                    ok=False,
                    error=str(getattr(exc, "message", None) or exc),
                    metadata={"plugin": PLUGIN_ID},
                )
        method = getattr(self._agent, self.method, None)
        if method is None or not callable(method):
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"nooa_method_missing:{self.method}",
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        try:
            raw = self._call_method(method, prompt, effective_workdir)
        except ExtensionMaterializeError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=str(getattr(exc, "message", None) or exc),
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"{type(exc).__name__}:{exc}",
                metadata={"plugin": PLUGIN_ID, "agent": self.agent_ref},
            )
        return _normalize_raw(
            raw, model=self.model, agent_ref=self.agent_ref, collect_dir=collect_dir
        )

    def _call_method(self, method: Any, prompt: str, workdir: str | None) -> Any:
        async def _async_call() -> Any:
            try:
                out = method(prompt, workdir=workdir)
            except TypeError:
                out = method(prompt)
            if inspect.isawaitable(out):
                return await out
            return out

        if inspect.iscoroutinefunction(method) or self._llm_backed:
            return _run_coro(_async_call())
        try:
            return method(prompt, workdir=workdir)
        except TypeError:
            return method(prompt)


def build_executor(**kwargs: Any) -> NooaExecutorSPI:
    """plugin.yaml provide entry: factory(**kwargs) -> ExecutorSPI."""
    return NooaExecutorSPI(**kwargs)
