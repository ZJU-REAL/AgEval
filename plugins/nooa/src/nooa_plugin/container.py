"""In-box nooa executor: run the baked worker through the box, not through docker.

The plugin no longer knows what kind of box it is in. It asks the environment to
run one command and reads the worker's JSON back, so the same code works for a
container, a sandbox or a remote machine.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from ageval.plugins.agent_result import AgentExecutor, AgentResult

WORKER_PATH = "/usr/local/bin/ageval-executor-nooa"
_ENV_API_KEYS = ("OPENAI_API_KEY", "litellm_api_key")
_ENV_BASE_URLS = ("OPENAI_BASE_URL", "litellm_base_url", "AGEVAL_OPENAI_BASE_URL")


class NooaBoxExecutor(AgentExecutor):
    """Invoke a task-local nooa agent inside the Attempt's box.

    The parent never imports the task's ``lib.agents``: the worker baked into the
    image does, on the far side of the box boundary.
    """

    kind = "nooa"

    def __init__(
        self,
        *,
        host: Any,
        placement: Any,
        agent_ref: str,
        method: str = "run",
        model: str = "nooa",
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self._host = host
        self._placement = placement
        self.agent_ref = agent_ref
        self.method = method or "run"
        self.model = model or "nooa"
        self.base_url = (base_url or "").strip() or None
        self.api_key_env = (api_key_env or "").strip() or None

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        return None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del redaction_sentinels
        request = {
            "prompt": prompt,
            "agent": self.agent_ref,
            "method": self.method,
            "model": self.model,
            "workdir": self._placement.workdir,
        }
        base_url = self._first_env(_ENV_BASE_URLS, self.base_url)
        api_key = self._first_env(_ENV_API_KEYS, None, locator=self.api_key_env)
        if base_url:
            request["api_base"] = base_url

        env = {"NOOA_MODEL": self.model}
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        if api_key:
            env["OPENAI_API_KEY"] = api_key

        result = asyncio.run(
            self._host.exec(
                ["python3", WORKER_PATH, json.dumps(request, sort_keys=True)],
                cwd=self._placement.workdir,
                env=env,
                timeout_sec=timeout,
            )
        )
        if result.exit_code != 0:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="nooa_worker_failed",
                stderr=result.stderr[-2000:],
                metadata={"executor_kind": self.kind, "exit_code": result.exit_code},
            )
        return self._result_from(result.stdout, collect_dir=collect_dir)

    def _result_from(self, stdout: str, *, collect_dir: str | None) -> AgentResult:
        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return AgentResult(
                model=self.model,
                text=stdout[-2000:],
                structured=None,
                ok=False,
                error="nooa_worker_unreadable",
                metadata={"executor_kind": self.kind},
            )
        if collect_dir:
            from pathlib import Path

            root = Path(collect_dir)
            root.mkdir(parents=True, exist_ok=True)
            (root / "nooa_worker.json").write_text(stdout, encoding="utf-8")
        text = str(payload.get("text") or "")
        structured = payload.get("structured")
        return AgentResult(
            model=str(payload.get("model") or self.model),
            text=text,
            structured=structured if isinstance(structured, dict) else None,
            ok=bool(payload.get("ok", True)),
            error=payload.get("error"),
            events=tuple(payload.get("events") or ()),
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            metadata={"executor_kind": self.kind, "agent": self.agent_ref},
        )

    def _first_env(
        self,
        names: tuple[str, ...],
        declared: str | None,
        *,
        locator: str | None = None,
    ) -> str | None:
        if declared:
            return declared
        for name in (locator, *names):
            value = os.environ.get(name or "", "").strip()
            if value:
                return value
        return None


__all__ = ["WORKER_PATH", "NooaBoxExecutor"]
