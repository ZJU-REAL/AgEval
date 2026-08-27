"""In-box evaluator socket: projected path, never a docker-unreachable host path."""

from __future__ import annotations

from types import SimpleNamespace

from ageval.evaluation.package_evaluator import _projected_agent_socket


def test_projected_socket_uses_host_method() -> None:
    host = SimpleNamespace(
        kind="docker",
        projected_agent_socket=lambda: "/ageval-agent.sock",
    )
    ctx = SimpleNamespace(agent_service=SimpleNamespace(socket_path="/tmp/host.sock"))
    assert _projected_agent_socket(ctx, host) == "/ageval-agent.sock"


def test_docker_without_projection_does_not_inherit_host_path() -> None:
    host = SimpleNamespace(kind="docker")
    ctx = SimpleNamespace(agent_service=SimpleNamespace(socket_path="/tmp/host.sock"))
    assert _projected_agent_socket(ctx, host) is None


def test_local_still_uses_parent_socket_path() -> None:
    host = SimpleNamespace(kind="local")
    ctx = SimpleNamespace(agent_service=SimpleNamespace(socket_path="/tmp/host.sock"))
    assert _projected_agent_socket(ctx, host) == "/tmp/host.sock"
