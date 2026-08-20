"""In-box nooa executor: run the worker through the environment Protocol."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
from typing import Any

from ageval.environments.protocol import HOME_PATH, WORKSPACE_PATH
from ageval.plugins.agent_result import AgentResult
from ageval.plugins.errors import ExtensionMaterializeError
from nooa_plugin import PLUGIN_ID

BOX_PLUGIN = f"{HOME_PATH}/_nooa"
BOX_WORKER = f"{BOX_PLUGIN}/ageval_executor_nooa.py"
BOX_SRC = f"{BOX_PLUGIN}/src"
BOX_PACKAGE = "/attempt/package"


def _run_coro(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class NooaBoxExecutor:
    """Invoke a task-local nooa agent inside the Attempt box via ``host.exec``."""

    kind = PLUGIN_ID

    def __init__(
        self,
        *,
        host: Any,
        placement: Any,
        plugin_root: Path,
        package_root: str | None,
        agent_ref: str,
        method: str,
        model: str,
        base_url: str | None,
        api_key_env: str | None,
    ) -> None:
        self._host = host
        self._placement = placement
        self._plugin_root = Path(plugin_root)
        self._package_root = Path(package_root) if package_root else None
        self.agent_ref = agent_ref
        self.method = method or "run"
        self.model = model
        self.base_url = (base_url or "").strip() or None
        self.api_key_env = (api_key_env or "").strip() or None
        self._prepared = False

    @staticmethod
    def describe() -> dict[str, Any]:
        from nooa_plugin.factory import describe_nooa

        return describe_nooa()

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
        try:
            return _run_coro(self._ainvoke(prompt, timeout=timeout, collect_dir=collect_dir))
        except ExtensionMaterializeError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=str(getattr(exc, "message", None) or exc),
                metadata={
                    "plugin": PLUGIN_ID,
                    "agent": self.agent_ref,
                    "execution_location": "attempt-container",
                },
            )

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
            "agent": self.agent_ref,
            "method": self.method,
            "model": self.model,
            "package_root": self._host.visible_path(BOX_PACKAGE),
            "workdir": self._host.visible_path(self._placement.workdir or WORKSPACE_PATH),
        }
        base = self._resolve_base_url()
        if base:
            request["api_base"] = base
        result = await self._host.exec(
            [
                *self._host.python_command,
                self._host.visible_path(BOX_WORKER),
                json.dumps(request, sort_keys=True),
            ],
            cwd=self._placement.workdir or WORKSPACE_PATH,
            env=self._exec_env(),
            timeout_sec=timeout,
        )
        return self._result_from(result, collect_dir=collect_dir)

    async def _prepare(self) -> None:
        if self._prepared:
            return
        await self._host.upload(
            self._plugin_root / "worker" / "ageval_executor_nooa.py", BOX_WORKER
        )
        await self._host.upload(self._plugin_root / "src" / "nooa_plugin", f"{BOX_SRC}/nooa_plugin")
        await self._upload_agent_module()
        self._prepared = True

    async def _upload_agent_module(self) -> None:
        if self._package_root is None or not self._package_root.is_dir():
            raise ExtensionMaterializeError(
                "nooa_package_root_missing",
                kind="extension_materialize_failed",
            )
        top = self.agent_ref.split(":", 1)[0].split(".", 1)[0]
        src = self._package_root / top
        file_src = self._package_root / f"{top}.py"
        if src.is_dir():
            await self._host.upload(src, f"{BOX_PACKAGE}/{top}")
            return
        if file_src.is_file():
            await self._host.upload(file_src, f"{BOX_PACKAGE}/{top}.py")
            return
        raise ExtensionMaterializeError(
            f"nooa_agent_source_missing:{top}",
            kind="extension_materialize_failed",
        )

    def _resolve_base_url(self) -> str | None:
        from nooa_plugin.factory import resolve_base_url

        return resolve_base_url(self.base_url)

    def _exec_env(self) -> dict[str, str]:
        from nooa_plugin.factory import resolve_api_key_value

        env: dict[str, str] = {
            "NOOA_MODEL": self.model,
            "PYTHONPATH": self._host.visible_path(BOX_SRC),
        }
        key = resolve_api_key_value(self.api_key_env)
        if key:
            env["OPENAI_API_KEY"] = key
        base = self._resolve_base_url()
        if base:
            env["OPENAI_BASE_URL"] = base
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
            (root / "nooa_worker.json").write_text(
                json.dumps(payload, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        if payload is None:
            return AgentResult(
                model=self.model,
                text=stdout[-2000:],
                structured=None,
                ok=False,
                error="nooa_worker_unreadable" if exit_code == 0 else "nooa_worker_failed",
                stderr=stderr[-2000:],
                metadata={
                    "plugin": PLUGIN_ID,
                    "agent": self.agent_ref,
                    "execution_location": "attempt-container",
                    "exit_code": exit_code,
                },
            )
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("plugin", PLUGIN_ID)
        metadata.setdefault("agent", self.agent_ref)
        metadata.setdefault("execution_location", "attempt-container")
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


__all__ = ["BOX_WORKER", "NooaBoxExecutor"]
