"""L1 nooa executor: docker exec into Attempt container (Spec 05 Ready)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from bora.adapters.agent_contract import AgentResult

WORKER_PATH = "/usr/local/bin/bora-executor-nooa"
PACKAGE_ROOT_CONTAINER = "/attempt/package"
WORKDIR_CONTAINER = "/attempt/workspace"


class NooaContainerExecutor:
    """Invoke package-local agents inside the Attempt container via baked worker.

    Parent never imports task ``lib.agents`` for L1 success path.
    """

    kind = "nooa"
    execution_location = "attempt-container"

    def __init__(
        self,
        *,
        container_id: str,
        agent_ref: str,
        method: str = "run",
        model: str = "nooa",
        uid: int = 10001,
        gid: int = 10001,
        package_root_container: str = PACKAGE_ROOT_CONTAINER,
        workdir_container: str = WORKDIR_CONTAINER,
    ) -> None:
        self.container_id = container_id
        self.agent_ref = agent_ref
        self.method = method or "run"
        self.model = model or "nooa"
        self.uid = uid
        self.gid = gid
        self.package_root_container = package_root_container
        self.workdir_container = workdir_container
        self.workdir = workdir_container
        self._ready = False

    def open(self, **kwargs: Any) -> None:
        del kwargs
        self._ready = True

    def close(self) -> None:
        self._ready = False

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del collect_dir, redaction_sentinels
        effective_workdir = workdir or self.workdir_container
        payload = {
            "prompt": prompt,
            "agent": self.agent_ref,
            "method": self.method,
            "package_root": self.package_root_container,
            "workdir": effective_workdir,
        }
        cmd = [
            "docker",
            "exec",
            "-i",
            "-u",
            f"{self.uid}:{self.gid}",
            "-w",
            effective_workdir,
            self.container_id,
            "python3",
            WORKER_PATH,
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=max(1.0, float(timeout)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="nooa_container_timeout",
                metadata={
                    "plugin": "nooa",
                    "execution_location": self.execution_location,
                    "agent": self.agent_ref,
                },
            )
        except OSError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"nooa_container_exec:{exc}",
                metadata={
                    "plugin": "nooa",
                    "execution_location": self.execution_location,
                },
            )

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "")[-2000:]
        if not stdout:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="nooa_container_empty_stdout",
                stderr=stderr,
                metadata={
                    "plugin": "nooa",
                    "execution_location": self.execution_location,
                    "returncode": proc.returncode,
                },
            )
        # Worker prints one JSON line (last non-empty line).
        line = stdout.splitlines()[-1]
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            return AgentResult(
                model=self.model,
                text=stdout[:2000],
                structured=None,
                ok=False,
                error="nooa_container_bad_json",
                stderr=stderr,
                metadata={
                    "plugin": "nooa",
                    "execution_location": self.execution_location,
                },
            )
        if not isinstance(doc, dict):
            return AgentResult(
                model=self.model,
                text=str(doc),
                structured=None,
                ok=False,
                error="nooa_container_result_not_object",
                metadata={"plugin": "nooa", "execution_location": self.execution_location},
            )
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        meta = {
            **meta,
            "plugin": "nooa",
            "execution_location": self.execution_location,
            "agent": self.agent_ref,
            "returncode": proc.returncode,
        }
        structured = doc.get("structured") if isinstance(doc.get("structured"), dict) else None
        return AgentResult(
            model=str(doc.get("model") or self.model),
            text=str(doc.get("text") or ""),
            structured=structured,
            ok=bool(doc.get("ok", False)),
            error=str(doc["error"]) if doc.get("error") else None,
            stderr=stderr,
            metadata=meta,
        )
