from __future__ import annotations

from typing import Any

from ageval.plugins.agent_result import AgentResult


def describe_host_probe() -> dict[str, Any]:
    return {
        "execution_mode": "container-worker",
        "tools": "unsupported",
        "structured_output": "unsupported",
        "session": "unsupported",
        "stream": "synthetic-lifecycle",
        "credential_env_names": ("PROBE_API_KEY",),
        "binary": "host-probe-bin",
    }


class HostProbeExecutor:
    kind = "host-probe"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    @staticmethod
    def describe() -> dict[str, Any]:
        return describe_host_probe()

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        return None

    def invoke(self, prompt: str, **kwargs: Any) -> AgentResult:
        del kwargs
        return AgentResult(model="host-probe", text=prompt, structured=None, ok=True)


def build_executor(**kwargs: Any) -> HostProbeExecutor:
    return HostProbeExecutor(**kwargs)
