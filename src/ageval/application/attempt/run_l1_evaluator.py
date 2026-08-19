"""L1 evaluator runners: isolated new container, or same-Attempt exec."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from ageval.config.constants import DEFAULT_EVAL_TMPFS_MB
from ageval.config.eval_placement import (
    PLACEMENT_WRITABLE,
    WORKDIR_ENV,
    WORKDIR_PATH,
    EvalPlacement,
)

_EVAL_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_REUSE_DEFAULT_USER = "12000:12000"
_REUSE_DEFAULT_HOME = "/actor-homes/default"
_EMPTY_CREDS = "/tmp/ageval-empty-creds"


def clean_eval_tmpfs_mount(tmpfs_mb: int, *, allow_exec: bool = False) -> str:
    """Docker ``--tmpfs`` spec for clean-eval ``/tmp``.

    ``allow_exec`` is only True for ``evaluation.placement: writable``.
    Size still comes from ``evaluation.tmpfs_mb`` (#133).
    """
    if not isinstance(tmpfs_mb, int) or isinstance(tmpfs_mb, bool) or tmpfs_mb < 1:
        raise ValueError("evaluation.tmpfs_mb must be a positive integer")
    exec_flag = "exec" if allow_exec else "noexec"
    return f"/tmp:rw,{exec_flag},nosuid,size={tmpfs_mb}m"


def _artifact_payload(
    artifact_key: str, artifact_filename: str, expected_filename: str | None
) -> str:
    arts = f'"artifacts": {{"{artifact_key}": "/eval/{artifact_filename}"'
    if expected_filename:
        arts += f', "expected": "/eval/{expected_filename}"'
    arts += "}"
    return arts


def _parse_eval_process(
    stdout: str,
    stderr: str,
    *,
    returncode: int,
    placement: str,
    extra_meta: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta: dict[str, Any] = {
        "ok": returncode == 0,
        "exit": returncode,
        "writer_stop_confirmed": True,
        "placement": placement,
        "stderr": (stderr or "")[-500:],
    }
    if extra_meta:
        meta.update(extra_meta)
    try:
        line = (stdout or "").strip().splitlines()[-1]
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raw = {"status": "ERROR", "score": None, "metrics": {}}
    except (json.JSONDecodeError, IndexError):
        raw = {
            "status": "ERROR",
            "score": None,
            "metrics": {"stderr": meta["stderr"], "stdout": (stdout or "")[-500:]},
        }
        meta["ok"] = False
    return raw, meta


def run_clean_evaluator_container(
    *,
    image_tag: str,
    staging: Path,
    artifact_filename: str,
    artifact_key: str,
    expected_filename: str | None,
    tmpfs_mb: int = DEFAULT_EVAL_TMPFS_MB,
    placement: EvalPlacement | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    arts = _artifact_payload(artifact_key, artifact_filename, expected_filename)
    script = textwrap.dedent(
        f"""
        import json, importlib.util
        from pathlib import Path
        pkg = Path("/attempt/package")
        leaked = pkg.exists() and ((pkg / "evaluation").exists() or any(pkg.iterdir()))
        if leaked:
            print(json.dumps({{"status": "ERROR", "score": None,
                               "metrics": {{"leak": "package_mount"}}}}))
            raise SystemExit(3)
        if Path("/creds").exists():
            print(json.dumps({{"status": "ERROR", "score": None,
                               "metrics": {{"leak": "credential"}}}}))
            raise SystemExit(3)
        spec = importlib.util.spec_from_file_location("ev", "/eval/evaluator.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.evaluate({{{arts}}})
        print(json.dumps(raw))
        """
    )
    if placement is None:
        clean_eval_tmpfs_mount(tmpfs_mb)
        spec = EvalPlacement(
            mode="staging",
            timeout_seconds=90.0,
            tmpfs_mb=tmpfs_mb,
            tmpfs_exec=False,
            network="none",
        )
    else:
        spec = placement
    name = f"ageval-eval-{staging.name[-8:]}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--user",
        "10001:10001",
        "--security-opt",
        "no-new-privileges",
        "--network",
        spec.network,
        "--read-only",
        "--tmpfs",
        clean_eval_tmpfs_mount(spec.tmpfs_mb, allow_exec=spec.tmpfs_exec),
        "-v",
        f"{staging}:/eval:ro",
        "--workdir",
        "/eval",
        # Package images may have a seed ENTRYPOINT; eval must not run it
        # (read-only root, no workspace mount).
        "--entrypoint",
        "python",
    ]
    if spec.mode == PLACEMENT_WRITABLE:
        cmd.extend(["-e", f"{WORKDIR_ENV}={WORKDIR_PATH}"])
    cmd.extend([image_tag, "-c", script])
    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=spec.timeout_seconds
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-fv", name], check=False, capture_output=True)
        return (
            {"status": "ERROR", "score": None, "metrics": {"error": "timeout"}},
            {
                "ok": False,
                "writer_stop_confirmed": True,
                "package_mounted": False,
                "placement": spec.mode,
                "reuse_attempt": False,
            },
        )
    return _parse_eval_process(
        proc.stdout or "",
        proc.stderr or "",
        returncode=proc.returncode,
        placement=spec.mode,
        extra_meta={"package_mounted": False, "reuse_attempt": False},
    )


def _hide_creds_cmds(container_id: str, image_tag: str) -> list[tuple[list[str], str]]:
    """Overlay empty /creds in the live container without changing its network."""
    return [
        (
            [
                "docker",
                "exec",
                "-u",
                "0:0",
                container_id,
                "mkdir",
                "-p",
                _EMPTY_CREDS,
                "/creds",
            ],
            "eval_creds_hide_mkdir_failed",
        ),
        (
            [
                "docker",
                "run",
                "--rm",
                "--privileged",
                "--user",
                "0:0",
                "--entrypoint",
                "nsenter",
                "--pid",
                f"container:{container_id}",
                "--network",
                "none",
                image_tag,
                "-t",
                "1",
                "-m",
                "mount",
                "--bind",
                _EMPTY_CREDS,
                "/creds",
            ],
            "eval_creds_hide_failed",
        ),
    ]


def run_reuse_attempt_evaluator(
    *,
    container_id: str,
    staging: Path,
    artifact_filename: str,
    artifact_key: str,
    expected_filename: str | None,
    placement: EvalPlacement,
    uid_gid: str | None = None,
    image_tag: str = "ageval-attempt:l1",
    actor_home: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run ``evaluator.py`` in the live Attempt container. No new eval box.

    Network stays whatever ``provider.network`` already is. Host credential
    env is not forwarded. Hidden inputs must already be on ``staging``.
    ``/creds`` is overlaid empty before exec; hide failure is ERROR.

    Actor ``HOME`` / ``PYTHONUSERBASE`` stay on the Attempt home so
    ``pip install --user`` packages remain importable. Host TOKEN/API_KEY
    env is still dropped via ``env -i``.
    """
    fail_meta = {
        "ok": False,
        "writer_stop_confirmed": True,
        "package_mounted": True,
        "placement": placement.mode,
        "reuse_attempt": True,
    }
    if not container_id:
        return (
            {"status": "ERROR", "score": None, "metrics": {"error": "missing_attempt_container"}},
            fail_meta,
        )

    arts = _artifact_payload(artifact_key, artifact_filename, expected_filename)
    script = textwrap.dedent(
        f"""
        import json, importlib.util, os
        from pathlib import Path
        for _k in os.environ:
            _u = _k.upper()
            if any(s in _u for s in ("TOKEN", "SECRET", "API_KEY", "PASSWORD")):
                print(json.dumps({{"status": "ERROR", "score": None,
                                   "metrics": {{"leak": "credential_env"}}}}))
                raise SystemExit(3)
        _creds = Path("/creds")
        if _creds.exists() and any(p.is_file() for p in _creds.rglob("*")):
            print(json.dumps({{"status": "ERROR", "score": None,
                               "metrics": {{"leak": "credential"}}}}))
            raise SystemExit(3)
        spec = importlib.util.spec_from_file_location("ev", "/eval/evaluator.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.evaluate({{{arts}}})
        print(json.dumps(raw))
        """
    )
    for cmd, err in (
        (
            ["docker", "exec", "-u", "0:0", container_id, "mkdir", "-p", "/eval"],
            "eval_mkdir_failed",
        ),
        (["docker", "cp", f"{staging}/.", f"{container_id}:/eval/"], "eval_copy_failed"),
        (
            ["docker", "exec", "-u", "0:0", container_id, "chmod", "-R", "a+rX", "/eval"],
            "eval_chmod_failed",
        ),
        *_hide_creds_cmds(container_id, image_tag),
    ):
        step = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if step.returncode != 0:
            return (
                {
                    "status": "ERROR",
                    "score": None,
                    "metrics": {"error": err, "stderr": (step.stderr or "")[-500:]},
                },
                fail_meta,
            )
    home = actor_home if actor_home else _REUSE_DEFAULT_HOME
    user = uid_gid if uid_gid else _REUSE_DEFAULT_USER
    cmd = [
        "docker",
        "exec",
        "-u",
        user,
        "-w",
        "/eval",
        container_id,
        "env",
        "-i",
        f"PATH={_EVAL_PATH}",
        f"HOME={home}",
        f"PYTHONUSERBASE={home}/.local",
        "python",
        "-c",
        script,
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=placement.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return (
            {"status": "ERROR", "score": None, "metrics": {"error": "timeout"}},
            fail_meta,
        )
    return _parse_eval_process(
        proc.stdout or "",
        proc.stderr or "",
        returncode=proc.returncode,
        placement=placement.mode,
        extra_meta={"package_mounted": True, "reuse_attempt": True},
    )
