"""Profile base_url + api_key (env locator) config validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw

REPO = Path(__file__).resolve().parents[2]


def _write_pkg(tmp: Path, *, slot_id: str = "glm") -> Path:
    pkg = tmp / "pkg"
    pkg.mkdir()
    (pkg / "harness.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    doc = {
        "format": "bora.task/1",
        "task_id": "profile-upstream",
        "harness": {"runtime": "python", "entrypoint": "harness:run"},
        "parameters": {},
        "provider": {"kind": "local", "assurance": "l0"},
        "agent_profiles": [{"id": slot_id}],
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
    (pkg / "task.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return pkg


def test_accepts_base_url_and_api_key_locator(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="glm")
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "profile-upstream",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings={
            "glm": {
                "executor": "Official/openai-http",
                "model": "glm-4.7",
                "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "api_key": "zhipu_coding_api_key",
            }
        },
    )
    profiles = thaw(locked.agent_profiles)
    assert profiles[0]["base_url"].startswith("https://")
    assert profiles[0]["api_key"] == "zhipu_coding_api_key"


def test_rejects_secret_like_api_key(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="bad")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(
            pkg,
            "profile-upstream",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings={
                "bad": {
                    "executor": "Official/openai-http",
                    "model": "glm-4.7",
                    "api_key": "sk-this-is-a-secret-value-not-a-locator",
                }
            },
        )
    assert "api_key" in str(ei.value).lower() or ei.value.error_code == "invalid_schema"


def test_rejects_non_url_base(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="bad")
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError):
        core.load_and_lock(
            pkg,
            "profile-upstream",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings={
                "bad": {
                    "executor": "Official/openai-http",
                    "model": "glm-4.7",
                    "base_url": "not-a-url",
                }
            },
        )


def test_resolve_executor_honors_profile_fields() -> None:
    from bora.adapters.agent_registry import resolve_executor

    ex = resolve_executor(
        "Official/openai-http",
        model="glm-4.7",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        api_key="zhipu_coding_api_key",
    )
    assert ex.model == "glm-4.7"
    assert ex.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert ex.api_key_env == "zhipu_coding_api_key"
