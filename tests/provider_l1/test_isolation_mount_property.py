"""Real Docker property probes for shared_write ACL and per-group workspaces.

Requires Docker daemon. Skips when unavailable.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from ageval.adapters.provider_docker import (
    DockerImageLock,
    DockerProvider,
    DockerRuntime,
    ensure_base_image,
)
from ageval.provider.isolation import parse_logical_topology
from ageval.provider.targets import IsolationMode
from ageval.runtime.identity import IdentityFactory


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def _prepare_runtime(tmp_path: Path) -> tuple[DockerProvider, DockerRuntime, Path]:
    root = Path.cwd()
    lock = ensure_base_image(root)
    # Use base image tag as package image for probe (no custom Dockerfile needed).
    img = DockerImageLock(
        kind="probe",
        platform=lock.platform,
        image_tag=lock.image_tag or "ageval-attempt:l1",
        image_digest=lock.image_digest,
        build_input_digest=lock.build_input_digest,
    )
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "0" * 64)
    attempt = factory.new_attempt(trial)
    docker = DockerProvider()
    work = tmp_path / "work"
    work.mkdir()
    # Minimal package root for filtered view.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dummy").write_text("x", encoding="utf-8")
    runtime = docker.prepare(
        attempt,
        package_root=pkg,
        work_root=work,
        network_mode="none",
        hide_evaluation=True,
        image_lock=img,
    )
    cred = work / "creds"
    cred.mkdir()
    (cred / "home").mkdir()
    (cred / "codex_home").mkdir()
    return docker, runtime, cred


def test_shared_container_shared_write_allow_deny(tmp_path: Path) -> None:
    docker, runtime, cred = _prepare_runtime(tmp_path)
    topo = parse_logical_topology(
        {
            "network": "none",
            "agent_isolation": {
                "mode": "shared-container",
                "groups": [
                    {
                        "id": "team",
                        "actors": [
                            {"id": "a1", "profiles": ["p"]},
                            {"id": "a2", "profiles": ["p"]},
                        ],
                        "shared_write": ["team"],
                    }
                ],
            },
        },
        profile_ids={"p"},
    )
    assert topo is not None
    assert topo.mode == IsolationMode.SHARED_CONTAINER
    try:
        ledger = docker.prepare_agent_targets(runtime, topo, cred_root=cred, network_mode="none")
        a1 = ledger.actors["a1"]
        a2 = ledger.actors["a2"]
        target = ledger.targets[a1.target_id]
        assert target.container_id
        assert a1.uid != a2.uid
        assert a1.shared_gid is not None

        # Allow: write under shared_write with primary group = shared_gid + umask 002.
        allow = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                f"{a1.uid}:{a1.shared_gid}",
                target.container_id,
                "sh",
                "-c",
                (
                    "umask 002; echo ok > /attempt/workspace/team/from_a1.txt"
                    " && cat /attempt/workspace/team/from_a1.txt"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert allow.returncode == 0, allow.stderr
        assert "ok" in (allow.stdout or "")

        # a2 can read/write shared path with its shared gid (group-writable file).
        peer = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                f"{a2.uid}:{a2.shared_gid}",
                target.container_id,
                "sh",
                "-c",
                (
                    "umask 002; echo peer >> /attempt/workspace/team/from_a1.txt"
                    " && cat /attempt/workspace/team/from_a1.txt"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert peer.returncode == 0, peer.stderr

        # Deny: write outside shared_write at workspace root (root-owned 0755).
        deny = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                f"{a1.uid}:{a1.shared_gid}",
                target.container_id,
                "sh",
                "-c",
                "echo bad > /attempt/workspace/not_shared.txt",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert deny.returncode != 0

        # HOME private: a2 cannot read a1 home.
        home = a1.home_container
        home_deny = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                f"{a2.uid}:{a2.gid}",
                target.container_id,
                "sh",
                "-c",
                f"cat {home}/.codex/auth.json 2>/dev/null || ls -la {home}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        # Either ls fails (permission) or cannot read private contents.
        # HOME is 0700 so ls as other user should fail.
        assert home_deny.returncode != 0 or "Permission denied" in (home_deny.stderr or "") + (
            home_deny.stdout or ""
        )
    finally:
        docker.cleanup(runtime)


def test_container_per_group_no_cross_group_workspace(tmp_path: Path) -> None:
    docker, runtime, cred = _prepare_runtime(tmp_path)
    topo = parse_logical_topology(
        {
            "network": "none",
            "agent_isolation": {
                "mode": "container-per-group",
                "groups": [
                    {"id": "g1", "actors": [{"id": "a1", "profiles": ["p"]}]},
                    {"id": "g2", "actors": [{"id": "a2", "profiles": ["p"]}]},
                ],
            },
        },
        profile_ids={"p"},
    )
    assert topo is not None
    try:
        ledger = docker.prepare_agent_targets(runtime, topo, cred_root=cred, network_mode="none")
        a1 = ledger.actors["a1"]
        a2 = ledger.actors["a2"]
        t1 = ledger.targets[a1.target_id]
        t2 = ledger.targets[a2.target_id]
        assert t1.target_id != t2.target_id
        assert t1.container_id and t2.container_id
        assert t1.container_id != t2.container_id

        # Distinct host workspace roots under group_ws/.
        assert runtime.workdir_host is not None
        g1 = runtime.workdir_host / "group_ws" / "g1"
        g2 = runtime.workdir_host / "group_ws" / "g2"
        assert g1.is_dir() and g2.is_dir()
        marker = f"secret-{uuid.uuid4().hex[:8]}"
        (g1 / "private.txt").write_text(marker, encoding="utf-8")

        # g2 container must not see g1's private file via /attempt/workspace.
        probe = subprocess.run(
            [
                "docker",
                "exec",
                t2.container_id,
                "sh",
                "-c",
                "cat /attempt/workspace/private.txt 2>&1 || true",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        out = (probe.stdout or "") + (probe.stderr or "")
        assert marker not in out

        # Mount inventory policy is recorded without docker ids.
        assert runtime.policy_digests.get("agent_workspace_mode") == "per_group"
    finally:
        docker.cleanup(runtime)
