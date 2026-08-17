"""L1 clean evaluator container — staging-only, network none, no package/creds."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from bora.config.constants import DEFAULT_EVAL_TMPFS_MB
from bora.config.eval_placement import (
    PLACEMENT_WRITABLE,
    WORKDIR_ENV,
    WORKDIR_PATH,
    EvalPlacement,
    resolve_eval_placement,
)


def clean_eval_tmpfs_mount(tmpfs_mb: int, *, allow_exec: bool = False) -> str:
    """Docker ``--tmpfs`` spec for clean-eval ``/tmp``.

    ``allow_exec`` is only True for ``evaluation.placement: writable``.
    Size still comes from ``evaluation.tmpfs_mb`` (#133).
    """
    if not isinstance(tmpfs_mb, int) or isinstance(tmpfs_mb, bool) or tmpfs_mb < 1:
        raise ValueError("evaluation.tmpfs_mb must be a positive integer")
    exec_flag = "exec" if allow_exec else "noexec"
    return f"/tmp:rw,{exec_flag},nosuid,size={tmpfs_mb}m"


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
    arts = f'"artifacts": {{"{artifact_key}": "/eval/{artifact_filename}"'
    if expected_filename:
        arts += f', "expected": "/eval/{expected_filename}"'
    arts += "}"
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
        )
    else:
        spec = placement
    name = f"bora-eval-{staging.name[-8:]}"
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
        "none",
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
            },
        )
    meta = {
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "writer_stop_confirmed": True,
        "package_mounted": False,
        "placement": spec.mode,
        "stderr": (proc.stderr or "")[-500:],
    }
    try:
        line = (proc.stdout or "").strip().splitlines()[-1]
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raw = {"status": "ERROR", "score": None, "metrics": {}}
    except (json.JSONDecodeError, IndexError):
        raw = {
            "status": "ERROR",
            "score": None,
            "metrics": {"stderr": meta["stderr"], "stdout": (proc.stdout or "")[-500:]},
        }
        meta["ok"] = False
    return raw, meta
