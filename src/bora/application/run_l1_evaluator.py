"""L1 clean evaluator container — staging-only, network none, no package/creds."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any


def run_clean_evaluator_container(
    *,
    image_tag: str,
    staging: Path,
    artifact_filename: str,
    artifact_key: str,
    expected_filename: str | None,
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
        "/tmp:rw,noexec,nosuid,size=32m",
        "-v",
        f"{staging}:/eval:ro",
        "--workdir",
        "/eval",
        image_tag,
        "python",
        "-c",
        script,
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
        return (
            {"status": "ERROR", "score": None, "metrics": {"error": "timeout"}},
            {"ok": False, "writer_stop_confirmed": True, "package_mounted": False},
        )
    meta = {
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "writer_stop_confirmed": True,
        "package_mounted": False,
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
