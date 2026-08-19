"""Binding overlays: path rules, lock existence, secret-free files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.helpers.lock import lock_with_profiles

from ageval.config.errors import ConfigError
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import thaw
from ageval.config.overlay_files import (
    normalize_overlay_path,
    overlay_secret_hits,
    parse_overlay_paths,
)
from ageval.config.package_fs import LocalPackageReader
from ageval.config.profiles import load_job_document


def _write_dataset(
    tmp: Path,
    *,
    bindings: dict[str, Any],
    overlay_files: dict[str, str] | None = None,
) -> Path:
    db = tmp / "db"
    (db / "tasks" / "t").mkdir(parents=True)
    (db / "ageval.yaml").write_text(
        "format: ageval.dataset/1\ndataset_id: example/overlays\nversion: '0.1.0'\n"
        "tasks:\n  root: tasks\n",
        encoding="utf-8",
    )
    (db / "profiles.yaml").write_text(
        yaml.safe_dump({"format": "ageval.profiles/1", "bindings": bindings}),
        encoding="utf-8",
    )
    task = db / "tasks" / "t"
    (task / "harness.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (task / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    (task / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "format": "ageval.task/1",
                "task_id": "t",
                "harness": {"runtime": "python", "entrypoint": "harness:run"},
                "parameters": {"models": {"default": "solver"}},
                "provider": {"kind": "local", "assurance": "l0"},
                "agent_profiles": [{"id": "solver"}],
                "limits": {
                    "wall_time_seconds": 60,
                    "agent_invocations": 1,
                    "environment_actions": 0,
                },
                "artifacts": {"publishable": []},
                "evaluation": {
                    "runtime": "python",
                    "entrypoint": "evaluator:evaluate",
                    "network": "none",
                    "inputs": [],
                    "output": {"format": "json"},
                },
            }
        ),
        encoding="utf-8",
    )
    for rel, text in (overlay_files or {}).items():
        path = db / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return db


def _lock(db: Path, bindings: dict[str, dict[str, Any]]):
    core = ConfigCore(package_reader=LocalPackageReader())
    return lock_with_profiles(
        db / "tasks" / "t",
        "t",
        bindings,
    )


def test_normalize_overlay_path_accepts_relative() -> None:
    assert normalize_overlay_path("overlays/AGENTS.md", location="t") == "overlays/AGENTS.md"
    assert parse_overlay_paths(
        ["overlays/skills/jsonl-agg", "overlays/skills/jsonl-agg"],
        location="t",
    ) == ["overlays/skills/jsonl-agg"]


@pytest.mark.parametrize(
    "raw",
    [
        "AGENTS.md",
        "overlays",
        "overlays/",
        "../overlays/x",
        "overlays/../secret",
        "/tmp/overlays/x",
        "~/overlays/x",
        "overlays//x",
        "",
    ],
)
def test_normalize_overlay_path_rejects_bad_shape(raw: str) -> None:
    with pytest.raises(ConfigError):
        normalize_overlay_path(raw, location="t")


def test_locator_forms_are_not_secrets() -> None:
    text = '{"apiKey": "{env:litellm_api_key}", "other": "$litellm_api_key"}'
    assert overlay_secret_hits(text) == []
    assert overlay_secret_hits("API key: see README") == []


def test_pem_and_token_are_secrets() -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n"
    assert "pem" in overlay_secret_hits(pem)
    assert "token" in overlay_secret_hits('token: "sk-abcdefghijklmnop"')
    entropy = "api_token = " + ("A7kQ9mN2pX4vB8wC1dE3fG5hJ6" * 2)
    assert overlay_secret_hits(entropy)


def test_omit_overlays_lock_unchanged(tmp_path: Path) -> None:
    db = _write_dataset(
        tmp_path,
        bindings={
            "solver": {
                "executor": "acp",
                "extensions": [{"plugin": "acp", "options": {"entry": "pi"}}],
                "model": "m",
            }
        },
    )
    locked = _lock(
        db,
        {
            "solver": {
                "executor": "acp",
                "extensions": [{"plugin": "acp", "options": {"entry": "pi"}}],
                "model": "m",
            }
        },
    )
    overlay = thaw(locked.job_overlay)
    assert "overlays" not in overlay["bindings"]["solver"]


def test_lock_requires_existing_overlay_path(tmp_path: Path) -> None:
    db = _write_dataset(
        tmp_path,
        bindings={"solver": {"executor": "mock", "model": "none"}},
    )
    with pytest.raises(ConfigError) as ei:
        _lock(
            db,
            {
                "solver": {
                    "executor": "mock",
                    "model": "none",
                    "overlays": ["overlays/missing.md"],
                }
            },
        )
    assert ei.value.error_code == "missing_reference"


def test_lock_accepts_file_and_directory(tmp_path: Path) -> None:
    db = _write_dataset(
        tmp_path,
        bindings={"solver": {"executor": "mock", "model": "none"}},
        overlay_files={
            "overlays/AGENTS.md": "# hello\n",
            "overlays/skills/jsonl-agg/SKILL.md": "# skill\n",
        },
    )
    bindings = {
        "solver": {
            "executor": "mock",
            "model": "none",
            "overlays": ["overlays/skills/jsonl-agg", "overlays/AGENTS.md"],
        }
    }
    locked = _lock(db, bindings)
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["overlays"] == [
        "overlays/skills/jsonl-agg",
        "overlays/AGENTS.md",
    ]


def test_lock_rejects_secret_in_overlay_file(tmp_path: Path) -> None:
    db = _write_dataset(
        tmp_path,
        bindings={"solver": {"executor": "mock", "model": "none"}},
        overlay_files={"overlays/secret.md": "-----BEGIN PRIVATE KEY-----\nabc\n"},
    )
    with pytest.raises(ConfigError) as ei:
        _lock(
            db,
            {
                "solver": {
                    "executor": "mock",
                    "model": "none",
                    "overlays": ["overlays/secret.md"],
                }
            },
        )
    assert ei.value.error_code == "invalid_package"
    assert "secret" in str(ei.value).lower()


def test_lock_allows_env_locator_in_overlay_json(tmp_path: Path) -> None:
    db = _write_dataset(
        tmp_path,
        bindings={"solver": {"executor": "mock", "model": "none"}},
        overlay_files={
            "overlays/cfg.json": '{"apiKey": "{env:litellm_api_key}"}\n',
        },
    )
    locked = _lock(
        db,
        {
            "solver": {
                "executor": "mock",
                "model": "none",
                "overlays": ["overlays/cfg.json"],
            }
        },
    )
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["overlays"] == ["overlays/cfg.json"]


def test_standalone_task_cannot_declare_overlays(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "harness.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    (pkg / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "format": "ageval.task/1",
                "task_id": "t",
                "harness": {"runtime": "python", "entrypoint": "harness:run"},
                "parameters": {"models": {"default": "solver"}},
                "provider": {"kind": "local", "assurance": "l0"},
                "agent_profiles": [{"id": "solver"}],
                "limits": {
                    "wall_time_seconds": 60,
                    "agent_invocations": 1,
                    "environment_actions": 0,
                },
                "artifacts": {"publishable": []},
                "evaluation": {
                    "runtime": "python",
                    "entrypoint": "evaluator:evaluate",
                    "network": "none",
                    "inputs": [],
                    "output": {"format": "json"},
                },
            }
        ),
        encoding="utf-8",
    )
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        lock_with_profiles(
            pkg,
            "t",
            {
                "solver": {
                    "executor": "mock",
                    "model": "none",
                    "overlays": ["overlays/AGENTS.md"],
                }
            },
        )
    assert ei.value.error_code == "invalid_package"


def test_profiles_document_normalizes_overlays(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "format": "ageval.profiles/1",
                "bindings": {
                    "solver": {
                        "executor": "mock",
                        "overlays": ["overlays/AGENTS.md"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bindings = load_job_document(path)
    assert bindings["solver"]["overlays"] == ["overlays/AGENTS.md"]
