"""Container-bound Agent executor — docker exec only, no host CLI fallback.

Used by ParentAgentService under L1 multi-actor / SDK scheduling.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bora.adapters.agent_contract import AgentResult
from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget


@dataclass
class ContainerCLIExecutor:
    """Invoke first-party CLI inside a bound ExecutionTarget as actor UID/GID."""

    kind: str
    model: str
    container_id: str  # private; never returned to harness
    actor: ActorPhysicalBinding
    target: ExecutionTarget
    env: dict[str, str]
    workdir: str = "/attempt/workspace"
    api_key_env: str | None = None
    base_url: str | None = None
    # Shared mutable counter: must stay zero for L1 acceptance.
    host_fallback_counter: list[int] | None = None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 300.0,
        collect_dir: str | Path | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
        workdir: str | None = None,
    ) -> AgentResult:
        del redaction_sentinels  # container path redacts via parent evidence store
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "skipped",
                        "reason": "offline_forced",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                    },
                ),
            )

        if self.target.state != "ready" or not self.container_id:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="target_dead",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "target_dead",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                        "target_id": self.target.target_id,
                        "generation": self.actor.generation,
                    },
                ),
            )

        if self.target.generation != self.actor.generation:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="generation_mismatch",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "generation_mismatch",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                        "target_id": self.target.target_id,
                        "session_generation": self.actor.generation,
                        "target_generation": self.target.generation,
                    },
                ),
            )

        binary_cmd = _cli_argv(self.kind, self.model, prompt)
        if binary_cmd is None:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="unsupported_capability",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "unsupported_capability",
                        "source": "container_executor",
                    },
                ),
            )

        # docker exec — never host binary.
        # When shared_write is granted, primary group is the shared GID so
        # 2770 shared paths are writable; HOME remains owner-writable (0700).
        # docker exec has no --group-add; primary-group switch is the v1 grant.
        run_gid = (
            self.actor.shared_gid
            if self.actor.shared_gid is not None and self.actor.shared_write
            else self.actor.gid
        )
        cmd = [
            "docker",
            "exec",
            "-u",
            f"{self.actor.uid}:{run_gid}",
            "-w",
            workdir or self.workdir,
        ]
        for key, val in self.env.items():
            if key.upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            cmd.extend(["-e", f"{key}={val}"])
        cmd.append(self.container_id)
        # Collaborative shared_write needs group-writable new files (umask 002).
        if self.actor.shared_gid is not None and self.actor.shared_write:
            cmd.extend(["sh", "-c", 'umask 002; exec "$@"', "bora-actor", *binary_cmd])
        else:
            cmd.extend(binary_cmd)

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            _maybe_collect(collect_dir, stdout, stderr)
            return AgentResult(
                model=self.model,
                text=stdout[-8000:],
                structured=_try_parse_structured(stdout),
                ok=False,
                error="TimeoutExpired",
                stderr=stderr[-8000:],
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "timeout",
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                        "target_id": self.target.target_id,
                        "actor_id": self.actor.actor_id,
                    },
                ),
            )
        except OSError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "crash",
                        "reason": type(exc).__name__,
                        "source": "container_executor",
                        "execution_location": "attempt-container",
                    },
                ),
            )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        _maybe_collect(collect_dir, stdout, stderr)
        structured = _try_parse_structured(stdout)
        text_body = json.dumps(structured) if structured is not None else stdout
        ok = proc.returncode == 0
        return AgentResult(
            model=self.model,
            text=(text_body or "")[-8000:],
            structured=structured,
            ok=ok,
            error=None if ok else f"exit_{proc.returncode}",
            stderr=stderr[-8000:],
            events=(
                {
                    "type": "lifecycle",
                    "phase": "terminal",
                    "returncode": proc.returncode,
                    "source": "container_executor",
                    "execution_location": "attempt-container",
                    "target_id": self.target.target_id,
                    "actor_id": self.actor.actor_id,
                    "generation": self.actor.generation,
                    "uid_class": "numeric_non_root",
                },
            ),
            source_refs=(),
        )


def _cli_argv(kind: str, model: str, prompt: str) -> list[str] | None:
    if kind == "codex":
        return [
            "codex",
            "exec",
            "--model",
            model,
            "--ephemeral",
            "--json",
            "--skip-git-repo-check",
            prompt,
        ]
    if kind == "pi":
        return [
            "pi",
            "-p",
            "--mode",
            "json",
            "--no-session",
            "--no-tools",
            "--model",
            model,
            prompt,
        ]
    if kind == "opencode":
        return [
            "opencode",
            "run",
            "--format",
            "json",
            "--model",
            model,
            "--pure",
            prompt,
        ]
    if kind in {"claude-code", "claude"}:
        return [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
            prompt,
        ]
    return None


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _maybe_collect(collect_dir: str | Path | None, stdout: str, stderr: str) -> None:
    if collect_dir is None:
        return
    root = Path(collect_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "backend-stdout.jsonl").write_text(stdout, encoding="utf-8")
    (root / "backend-stderr.txt").write_text(stderr, encoding="utf-8")


def _try_parse_structured(stdout: str) -> dict[str, Any] | None:
    raw = (stdout or "").strip()
    if not raw:
        return None
    # Prefer last JSON object from JSONL (codex --json).
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        # codex agent message content
        if "answer" in obj or "n" in obj:
            return obj
        msg = obj.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            parts = msg.get("content")
            if isinstance(parts, list):
                blobs = [
                    p.get("text", "")
                    for p in parts
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                joined = "\n".join(str(b) for b in blobs).strip()
                parsed = _extract_json_object(joined)
                if parsed is not None:
                    return parsed
        # item.completed / agent_message shapes
        item = obj.get("item")
        if isinstance(item, dict):
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                parsed = _extract_json_object(text)
                if parsed is not None:
                    return parsed
        content = obj.get("content")
        if isinstance(content, str):
            parsed = _extract_json_object(content)
            if parsed is not None:
                return parsed
    return _extract_json_object(raw)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def new_opaque_target_id() -> str:
    return f"tgt_{uuid.uuid4().hex[:16]}"
