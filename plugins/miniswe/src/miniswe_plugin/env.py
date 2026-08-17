"""Bash environments for mini-swe-agent.

L0 runs on the host. L1 execs into a Core-owned container — this module
never starts or stops Docker containers.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any

SUBMIT_MARK = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def build_docker_exec_argv(
    *,
    container_id: str,
    command: str,
    uid: int,
    gid: int,
    workdir: str,
) -> list[str]:
    return [
        "docker",
        "exec",
        "-u",
        f"{uid}:{gid}",
        "-w",
        workdir,
        container_id,
        "bash",
        "-lc",
        command,
    ]


def _check_submitted(output: dict[str, Any]) -> None:
    lines = str(output.get("output") or "").lstrip().splitlines(keepends=True)
    if not lines or lines[0].strip() != SUBMIT_MARK:
        return
    if int(output.get("returncode") or 0) != 0:
        return
    submission = "".join(lines[1:])
    try:
        from minisweagent.exceptions import Submitted
    except ImportError:
        return
    raise Submitted(
        {
            "role": "exit",
            "content": submission,
            "extra": {"exit_status": "Submitted", "submission": submission},
        }
    )


class LocalBashEnv:
    """Host subprocess bash. Duck-types minisweagent.Environment."""

    def __init__(self, *, cwd: str, timeout: int = 30) -> None:
        self.cwd = cwd
        self.timeout = timeout
        self.config = type("Cfg", (), {"cwd": cwd, "timeout": timeout})()

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = str(action.get("command") or "")
        work = cwd or self.cwd or os.getcwd()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                text=True,
                cwd=work,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout or self.timeout,
            )
            out: dict[str, Any] = {
                "output": proc.stdout or "",
                "returncode": proc.returncode,
                "exception_info": "",
            }
        except Exception as exc:  # noqa: BLE001
            out = {
                "output": "",
                "returncode": -1,
                "exception_info": f"{type(exc).__name__}:{exc}",
            }
        _check_submitted(out)
        return out

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        u = platform.uname()
        return {
            "system": u.system,
            "release": u.release,
            "version": u.version,
            "machine": u.machine,
            **kwargs,
        }

    def serialize(self) -> dict[str, Any]:
        return {
            "info": {
                "config": {
                    "environment": {"cwd": self.cwd, "kind": "local"},
                    "environment_type": "miniswe_plugin.env.LocalBashEnv",
                }
            }
        }


class DockerExecEnv:
    """docker exec into a Runtime-owned Attempt container."""

    def __init__(
        self,
        *,
        container_id: str,
        uid: int,
        gid: int,
        workdir: str,
        timeout: int = 30,
    ) -> None:
        self.container_id = container_id
        self.uid = uid
        self.gid = gid
        self.workdir = workdir
        self.timeout = timeout
        self.config = type("Cfg", (), {"cwd": workdir, "timeout": timeout})()

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = str(action.get("command") or "")
        work = cwd or self.workdir
        argv = build_docker_exec_argv(
            container_id=self.container_id,
            command=command,
            uid=self.uid,
            gid=self.gid,
            workdir=work,
        )
        try:
            proc = subprocess.run(
                argv,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout or self.timeout,
            )
            out: dict[str, Any] = {
                "output": proc.stdout or "",
                "returncode": proc.returncode,
                "exception_info": "",
            }
        except Exception as exc:  # noqa: BLE001
            out = {
                "output": "",
                "returncode": -1,
                "exception_info": f"{type(exc).__name__}:{exc}",
            }
        _check_submitted(out)
        return out

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "system": "Linux",
            "release": "container",
            "version": "l1",
            "machine": "x86_64",
            "container_id": self.container_id,
            **kwargs,
        }

    def serialize(self) -> dict[str, Any]:
        return {
            "info": {
                "config": {
                    "environment": {
                        "kind": "docker_exec",
                        "container_id": self.container_id,
                        "workdir": self.workdir,
                    },
                    "environment_type": "miniswe_plugin.env.DockerExecEnv",
                }
            }
        }
