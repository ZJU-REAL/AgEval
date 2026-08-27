"""Evaluate-host docker boxes can mount the parent socket; agent boxes cannot."""

from __future__ import annotations

from pathlib import Path

from ageval.environments.protocol import AGENT_SERVICE_SOCK_PATH, BoxSpec
from ageval.plugins.contrib.docker.host import DockerHost


def _spec(tmp_path: Path, *, socket: Path | None = None) -> BoxSpec:
    return BoxSpec(
        attempt_root=tmp_path / "box",
        task_root=tmp_path,
        repo_root=tmp_path,
        agent_service_socket=socket,
    )


def test_evaluate_host_volume_flags_include_parent_socket(tmp_path: Path) -> None:
    sock = tmp_path / "agent.sock"
    sock.write_bytes(b"")
    host = DockerHost(spec=_spec(tmp_path, socket=sock), options={"image": "ageval-attempt:base"})
    flags = host._volume_flags()
    assert flags[0:2] == ["-v", f"{host.root}:/attempt"]
    assert ["-v", f"{sock.resolve()}:{AGENT_SERVICE_SOCK_PATH}"] == flags[2:4]
    assert host.projected_agent_socket() == AGENT_SERVICE_SOCK_PATH
    assert "docker.sock" not in " ".join(flags)
    assert "DOCKER_HOST" not in " ".join(flags)


def test_agent_host_does_not_mount_parent_socket(tmp_path: Path) -> None:
    host = DockerHost(spec=_spec(tmp_path), options={"image": "ageval-attempt:base"})
    flags = host._volume_flags()
    assert AGENT_SERVICE_SOCK_PATH not in " ".join(flags)
    assert host.projected_agent_socket() is None
    env = host._env_flags({})
    assert not any("AGEVAL_AGENT_SERVICE_SOCK" in part for part in env)
