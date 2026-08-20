"""In-box dsh executor: run the worker through the environment Protocol."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
from typing import Any

from ageval.environments.protocol import HOME_PATH, WORKSPACE_PATH
from ageval.plugins.agent_result import AgentResult
from dsh_plugin import PLUGIN_ID

BOX_PLUGIN = f"{HOME_PATH}/_dsh"
BOX_WORKER = f"{BOX_PLUGIN}/ageval_executor_dsh.py"
BOX_SRC = f"{BOX_PLUGIN}/src"
BOX_COMPOSITIONS = f"{BOX_PLUGIN}/compositions"
BOX_SESSIONS = f"{HOME_PATH}/dsh-sessions"


def _run_coro(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class DshBoxExecutor:
    """Invoke DeepSeek Harness inside the Attempt box via ``host.exec``."""

    kind = PLUGIN_ID

    def __init__(
        self,
        *,
        host: Any,
        placement: Any,
        plugin_root: Path,
        model: str,
        provider: str,
        composition: str,
        permission: str | None,
        base_url: str | None,
        api_key_env: str | None,
        session_id: str,
    ) -> None:
        self._host = host
        self._placement = placement
        self._plugin_root = Path(plugin_root)
        self.model = model
        self.provider = provider
        self.composition = composition
        self.permission = permission
        self.base_url = (base_url or "").strip() or None
        self.api_key_env = (api_key_env or "").strip() or None
        self.session_id = session_id
        self._prepared = False

    @staticmethod
    def describe() -> dict[str, Any]:
        from dsh_plugin.factory import describe_dsh

        return describe_dsh()

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        return None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        collect_dir: str | os.PathLike[str] | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del redaction_sentinels
        return _run_coro(self._ainvoke(prompt, timeout=timeout, collect_dir=collect_dir))

    async def _ainvoke(
        self,
        prompt: str,
        *,
        timeout: float,
        collect_dir: str | os.PathLike[str] | None,
    ) -> AgentResult:
        await self._prepare()
        request = {
            "prompt": prompt,
            "model": self.model,
            "provider": self.provider,
            "workdir": self._host.visible_path(self._placement.workdir or WORKSPACE_PATH),
            "session_root": self._host.visible_path(BOX_SESSIONS),
            "cordis": self._host.visible_path(
                f"{BOX_COMPOSITIONS}/{self.composition}.cordis.yml"
            ),
            "session_id": self.session_id,
            "composition": self.composition,
        }
        if self.permission:
            request["permission"] = self.permission
        env = self._exec_env()
        result = await self._host.exec(
            [
                *self._host.python_command,
                self._host.visible_path(BOX_WORKER),
                json.dumps(request, sort_keys=True),
            ],
            cwd=self._placement.workdir or WORKSPACE_PATH,
            env=env,
            timeout_sec=timeout,
        )
        return self._result_from(result, collect_dir=collect_dir)

    async def _prepare(self) -> None:
        if self._prepared:
            return
        await self._host.upload(self._plugin_root / "worker" / "ageval_executor_dsh.py", BOX_WORKER)
        await self._host.upload(self._plugin_root / "src" / "dsh_plugin", f"{BOX_SRC}/dsh_plugin")
        await self._host.upload(self._plugin_root / "compositions", BOX_COMPOSITIONS)
        self._prepared = True

    def _exec_env(self) -> dict[str, str]:
        from dsh_plugin.factory import PERMISSION_ENV, resolve_api_key_value, resolve_base_url

        env: dict[str, str] = {
            "DSH_MODEL": self.model,
            "PYTHONPATH": self._host.visible_path(BOX_SRC),
            "DSH_CORDIS_CONFIG": self._host.visible_path(
                f"{BOX_COMPOSITIONS}/{self.composition}.cordis.yml"
            ),
        }
        key = resolve_api_key_value(self.api_key_env)
        if key:
            env["DEEPSEEK_API_KEY"] = key
        base = resolve_base_url(self.base_url)
        if base:
            env["DEEPSEEK_BASE_URL"] = base
        if self.permission:
            env[PERMISSION_ENV] = self.permission
        if os.environ.get("AGEVAL_OFFLINE_AGENT") == "1":
            env["AGEVAL_OFFLINE_AGENT"] = "1"
        return env

    def _result_from(self, result: Any, *, collect_dir: str | os.PathLike[str] | None) -> AgentResult:
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        exit_code = int(getattr(result, "exit_code", 1) or 0)
        payload = _payload_from_stdout(stdout)
        if collect_dir and payload is not None:
            root = Path(collect_dir)
            root.mkdir(parents=True, exist_ok=True)
            (root / "dsh_worker.json").write_text(
                json.dumps(payload, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        if payload is None:
            return AgentResult(
                model=self.model,
                text=stdout[-2000:],
                structured=None,
                ok=False,
                error="dsh_worker_unreadable" if exit_code == 0 else "dsh_worker_failed",
                stderr=stderr[-2000:],
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": "attempt-container",
                    "exit_code": exit_code,
                },
            )
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("plugin", PLUGIN_ID)
        metadata.setdefault("execution_location", "attempt-container")
        metadata["composition"] = self.composition
        if self.permission:
            metadata["permission"] = self.permission
        structured = payload.get("structured")
        events = payload.get("events") or ()
        usage = payload.get("usage")
        return AgentResult(
            model=str(payload.get("model") or self.model),
            text=str(payload.get("text") or ""),
            structured=structured if isinstance(structured, dict) else None,
            ok=bool(payload.get("ok", True)),
            error=str(payload["error"]) if payload.get("error") else None,
            stderr=stderr[-2000:],
            events=tuple(events) if isinstance(events, list) else (),
            usage=usage if isinstance(usage, dict) else None,
            metadata=metadata,
        )


def _payload_from_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text.splitlines()[-1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


__all__ = ["BOX_WORKER", "DshBoxExecutor"]
