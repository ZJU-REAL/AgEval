"""L1 dsh executor: docker exec the baked in-container worker."""

from __future__ import annotations

import json
from typing import Any

from bora.adapters.agent_container import wrap_docker_exec
from bora.adapters.agent_contract import AgentExecutor, AgentResult
from bora.adapters.provider_docker.cli_supervise import supervise_docker_cli
from bora.provider.contract import TerminationPolicy
from bora.provider.outcomes import ProcessTerminalKind
from dsh_plugin import PLUGIN_ID
from dsh_plugin.factory import (
    DEFAULT_COMPOSITION,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    resolve_api_key_value,
    resolve_base_url,
)

WORKER_PATH = "/usr/local/bin/bora-executor-dsh"
CORDIS_CONTAINER = "/opt/dsh/compositions/slim.cordis.yml"
WORKDIR_CONTAINER = "/attempt/workspace"
HOME_CONTAINER = "/attempt/home"


class DshContainerExecutor(AgentExecutor):
    """Invoke DeepSeekHarness inside the Attempt container via baked worker."""

    kind = PLUGIN_ID
    execution_location = "attempt-container"

    def __init__(
        self,
        *,
        container_id: str,
        model: str = DEFAULT_MODEL,
        provider: str = DEFAULT_PROVIDER,
        composition: str = DEFAULT_COMPOSITION,
        base_url: str | None = None,
        api_key_env: str | None = None,
        uid: int = 10001,
        gid: int = 10001,
        workdir_container: str = WORKDIR_CONTAINER,
        home_container: str = HOME_CONTAINER,
        session_id: str | None = None,
    ) -> None:
        self.container_id = container_id
        self.model = model or DEFAULT_MODEL
        self.provider = provider or DEFAULT_PROVIDER
        self.composition = composition or DEFAULT_COMPOSITION
        self.base_url = (base_url or "").strip() or None
        self.api_key_env = (api_key_env or "").strip() or None
        self.uid = uid
        self.gid = gid
        self.workdir_container = workdir_container
        self.home_container = home_container
        self.workdir = workdir_container
        self.session_id = session_id
        self._ready = False

    def open(self, **kwargs: Any) -> None:
        del kwargs
        self._ready = True

    def close(self) -> None:
        self._ready = False

    def _child_env(self) -> dict[str, str]:
        env: dict[str, str] = {
            "DSH_CWD": self.workdir_container,
            "DSH_SESSION_ROOT": f"{self.home_container.rstrip('/')}/dsh-sessions",
            "DSH_CORDIS_CONFIG": CORDIS_CONTAINER,
        }
        key = resolve_api_key_value(self.api_key_env)
        if key:
            env["DEEPSEEK_API_KEY"] = key
        base = resolve_base_url(self.base_url)
        if base:
            env["DEEPSEEK_BASE_URL"] = base
        return env

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del redaction_sentinels
        effective_workdir = workdir or self.workdir_container
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": self.model,
            "provider": self.provider,
            "composition": self.composition,
            "workdir": effective_workdir,
            "session_root": f"{self.home_container.rstrip('/')}/dsh-sessions",
            "cordis": CORDIS_CONTAINER,
            "session_id": self.session_id,
        }
        env = self._child_env()
        env["DSH_CWD"] = effective_workdir
        cmd = wrap_docker_exec(
            container_id=self.container_id,
            uid=self.uid,
            gid=self.gid,
            workdir=effective_workdir,
            env=env,
            argv=["python3", WORKER_PATH],
        )
        teardown_requested = {"value": False}

        def _terminate() -> str | None:
            teardown_requested["value"] = True
            return None

        def _is_alive() -> bool:
            return teardown_requested["value"]

        try:
            outcome = supervise_docker_cli(
                cmd,
                timeout_seconds=max(1.0, float(timeout)),
                stdin_bytes=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                termination=TerminationPolicy(terminate=_terminate, is_alive=_is_alive),
            )
        except FileNotFoundError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"dsh_container_exec:{exc}",
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                },
            )

        if outcome.terminal == ProcessTerminalKind.TIMED_OUT:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="dsh_timeout",
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                },
            )
        if outcome.terminal == ProcessTerminalKind.SPAWN_FAILED:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"dsh_container_exec:{(outcome.stderr_summary or '')[:200]}",
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                },
            )

        stdout = (outcome.stdout_summary or "").strip()
        stderr = (outcome.stderr_summary or "")[-2000:]
        if not stdout:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="dsh_container_empty_stdout",
                stderr=stderr,
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                    "returncode": outcome.exit_code,
                },
            )
        line = stdout.splitlines()[-1]
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            return AgentResult(
                model=self.model,
                text=stdout[:2000],
                structured=None,
                ok=False,
                error="dsh_container_bad_json",
                stderr=stderr,
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                },
            )
        if not isinstance(doc, dict):
            return AgentResult(
                model=self.model,
                text=str(doc),
                structured=None,
                ok=False,
                error="dsh_container_result_not_object",
                metadata={
                    "plugin": PLUGIN_ID,
                    "execution_location": self.execution_location,
                },
            )
        base_meta: dict[str, Any] = {}
        raw_meta = doc.get("metadata")
        if isinstance(raw_meta, dict):
            base_meta = {str(k): v for k, v in raw_meta.items()}
        structured = doc.get("structured") if isinstance(doc.get("structured"), dict) else None
        raw_events = doc.get("events")
        events: tuple[dict[str, Any], ...] = ()
        if isinstance(raw_events, list):
            events = tuple(e for e in raw_events if isinstance(e, dict))
        raw_native = doc.get("native_events")
        native: list[dict[str, Any]] = []
        if isinstance(raw_native, list):
            native = [e for e in raw_native if isinstance(e, dict)]
        usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else None
        meta: dict[str, Any] = {
            **base_meta,
            "plugin": PLUGIN_ID,
            "execution_location": self.execution_location,
            "returncode": outcome.exit_code,
            "native_event_count": len(native),
        }
        if collect_dir and native:
            from pathlib import Path

            root = Path(collect_dir)
            root.mkdir(parents=True, exist_ok=True)
            (root / "dsh_events.jsonl").write_text(
                "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in native) + "\n",
                encoding="utf-8",
            )
        return AgentResult(
            model=str(doc.get("model") or self.model),
            text=str(doc.get("text") or ""),
            structured=structured,
            ok=bool(doc.get("ok", False)),
            error=str(doc["error"]) if doc.get("error") else None,
            stderr=stderr,
            events=events,
            usage=usage,
            metadata=meta,
        )
